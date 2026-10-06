"""Prospective shadow forecasts from official NBA scorer gamebooks.

This module is deliberately isolated from the production OfficialNBAProvider.
It creates no market decision, no stake and no certification. Its purpose is to
collect point-in-time predictive evidence for a possible future provider
fallback while stats.nba.com remains inaccessible on hosted runners.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .communications_schedule import (
    ReferenceScheduleGame,
    as_pregame_schedule,
)
from .gamebook_stats import resolve_gamebook_schedule, run as build_gamebook_pack
from .injury_pdf import fetch_latest_report, game_report_ready
from .lineage import build_input_manifest
from .live_inputs import team_id, team_metric_from_pack
from .rotation_projection import project_rotation
from .schedule import games_on, season_for_date
from .schedule_context import build_game_context
from .snapshot_store import persist_snapshot
from .structural import project_game
from .teams import canonical_team
from .tracking import append_jsonl
from .distribution import normal_cdf

ROLE = "ALTERNATE_PROVIDER_SHADOW"
GENERATION = "pulsar-nba-gamebook-provider-shadow-v1"
MIN_COMPLETED_TEAM_GAMES = 5
MIN_GAMEBOOK_COMPLETENESS = 1.0
SCHEDULE_CACHE_SCHEMA = "pulsar-nba-shadow-schedule-cache-v2"
SCHEDULE_CACHE_MAX_AGE_HOURS = 24.0


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp requires timezone")
    return parsed.astimezone(timezone.utc)


def _minutes_to(commence: str, now: datetime) -> float:
    return (_dt(commence) - now).total_seconds() / 60.0


def _injury_map(report: dict[str, Any], team: str, game_date: str) -> dict[str, str]:
    return {
        str(row["player_name"]): str(row["status"])
        for row in report.get("records") or []
        if canonical_team(str(row.get("team") or "")) == canonical_team(team)
        and row.get("game_date") == game_date
    }


def _existing(path: str | Path) -> set[str]:
    target = Path(path)
    if not target.exists():
        return set()
    rows: set[str] = set()
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.add(str(json.loads(line).get("entry_key") or ""))
        except (ValueError, TypeError):
            continue
    return rows


def _status(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")



def _reference_schedule_cached(
    *,
    season: str,
    now: datetime,
    cache_path: str | Path,
) -> list[ReferenceScheduleGame]:
    target=Path(cache_path)
    if target.exists():
        try:
            payload=json.loads(target.read_text(encoding="utf-8"))
            generated=_dt(str(payload["generated_at"]))
            age_hours=(now-generated).total_seconds()/3600.0
            rows=[ReferenceScheduleGame(**row) for row in payload["games"]]
            if (
                payload.get("schema")==SCHEDULE_CACHE_SCHEMA
                and payload.get("season")==season
                and -0.1 <= age_hours <= SCHEDULE_CACHE_MAX_AGE_HOURS
                and len(rows)>=1000
            ):
                return rows
        except (OSError,ValueError,TypeError,KeyError):
            pass
    rows=resolve_gamebook_schedule(season=season)
    if len(rows)<1000:
        raise RuntimeError("NBA shadow schedule cache refresh too small")
    payload={
        "schema":SCHEDULE_CACHE_SCHEMA,
        "season":season,
        "generated_at":now.isoformat(),
        "games":[asdict(row) for row in rows],
    }
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(payload,sort_keys=True,separators=(",",":")),encoding="utf-8")
    return rows

def run(
    *,
    target_date: str,
    output: str = "runtime/provider_shadow/gamebook_forecasts.jsonl",
    status_output: str = "runtime/provider_shadow/status.json",
    cache_root: str = "runtime/gamebook_reference",
    stat_pack_output: str = "runtime/gamebook_reference/stat_pack.json",
    snapshot_root: str = "runtime/provider_shadow/snapshots",
    schedule_cache_path: str = "runtime/provider_shadow/communications_schedule.json",
    max_network_games: int = 60,
    now: datetime | None = None,
    reference_schedule: list[Any] | None = None,
    stat_pack: dict[str, Any] | None = None,
    injuries: dict[str, Any] | None = None,
) -> dict[str, Any]:
    requested_now = now
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    season = season_for_date(target_date)
    result: dict[str, Any] = {
        "schema": "pulsar-nba-gamebook-provider-shadow-status-v1",
        "role": ROLE,
        "generation": GENERATION,
        "target_date": target_date,
        "checked_at": current.isoformat(),
        "status": "STARTED",
        "added": 0,
        "candidate_games": 0,
        "production_provider_authorized": False,
        "predictive_authority": False,
        "market_data_used": False,
        "betting_certified": False,
        "failures": [],
    }

    try:
        reference = (
            list(reference_schedule)
            if reference_schedule is not None
            else _reference_schedule_cached(
                season=season,now=current,cache_path=schedule_cache_path
            )
        )
        schedule = as_pregame_schedule(reference, target_date=target_date)
        slate = [
            game for game in games_on(schedule, target_date)
            if _minutes_to(game.commence_time, current) > 0
        ]
        if not slate:
            result["status"] = "NO_UPCOMING_GAMES"
            _status(status_output, result)
            return result
        final_window = [
            game for game in slate
            if 5 <= _minutes_to(game.commence_time, current) <= 30
        ]
        if not final_window:
            result["status"] = "NO_ELIGIBLE_FINAL_WINDOW"
            result["upcoming_games"] = len(slate)
            result["source_fetch_deferred"] = True
            _status(status_output, result)
            return result

        pack = stat_pack if stat_pack is not None else build_gamebook_pack(
            season=season,
            target_date=target_date,
            cache_root=cache_root,
            output=stat_pack_output,
            max_network_games=max_network_games,
            schedule=reference,
        )
        if pack.get("role") != "ALTERNATE_REFERENCE_ONLY":
            raise ValueError("gamebook stat pack role mismatch")
        if pack.get("production_provider_authorized") is not False:
            raise ValueError("gamebook stat pack has forbidden production authority")
        if pack.get("season") != season:
            raise ValueError("gamebook stat pack season mismatch")
        completeness = float(pack.get("gamebook_completeness") or 0.0)
        if completeness < MIN_GAMEBOOK_COMPLETENESS or not pack.get("collection_complete"):
            result["status"] = "INCOMPLETE_GAMEBOOK_HISTORY"
            result["gamebook_completeness"] = completeness
            result["missing_gamebooks"] = len(pack.get("missing_gamebooks") or [])
            _status(status_output, result)
            return result

        report = injuries if injuries is not None else fetch_latest_report(season=season)
        if not report.get("team_status"):
            raise ValueError("official injury report has no team submission rows")
        injury_snapshot = persist_snapshot(
            snapshot_root,
            kind="injuries",
            observed_at=report["reported_at"],
            payload=report,
            source=report.get("source_url") or "official-nba",
        )
    except Exception as exc:
        result["status"] = "SOURCE_UNAVAILABLE"
        result["failures"].append(f"{type(exc).__name__}:{exc}")
        _status(status_output, result)
        return result

    # Analysis time is captured AFTER source acquisition. In tests an explicit
    # deterministic clock is honored. Re-checking the FINAL window below then
    # protects against a slow source request crossing tipoff.
    current = (
        requested_now.astimezone(timezone.utc)
        if requested_now is not None
        else datetime.now(timezone.utc)
    )
    result["checked_at"] = current.isoformat()

    # Context may use the full official Communications schedule, but neutral-site
    # rows are excluded because that source does not designate home/away.
    context_schedule = as_pregame_schedule(reference)
    team_rows = (pack.get("advanced_windows") or {}).get(0) or (
        pack.get("advanced_windows") or {}
    ).get("0") or []
    games_played = {
        canonical_team(str(row.get("TEAM_NAME") or "")): int(row.get("GP") or 0)
        for row in team_rows
    }

    seen = _existing(output)
    added = 0
    eligible = 0
    for game in final_window:
        try:
            minutes = _minutes_to(game.commence_time, current)
            if not 5 <= minutes <= 30:
                continue
            if not game_report_ready(
                report, game_date=game.game_date, home=game.home, away=game.away
            ):
                raise ValueError("target game injury report not submitted for both teams")
            if min(
                games_played.get(canonical_team(game.home), 0),
                games_played.get(canonical_team(game.away), 0),
            ) < MIN_COMPLETED_TEAM_GAMES:
                raise ValueError(
                    f"fewer than {MIN_COMPLETED_TEAM_GAMES} completed team games"
                )

            home = team_metric_from_pack(game.home, pack, home=True)
            away = team_metric_from_pack(game.away, pack, home=False)
            home_rotation = project_rotation(
                team_id(game.home),
                season_base=pack["player_season"],
                recent_base=pack["player_recent"],
                season_advanced=pack["player_advanced"],
                team_ortg=home.ortg,
                team_drtg=home.drtg,
                injury_status=_injury_map(report, game.home, game.game_date),
            )
            away_rotation = project_rotation(
                team_id(game.away),
                season_base=pack["player_season"],
                recent_base=pack["player_recent"],
                season_advanced=pack["player_advanced"],
                team_ortg=away.ortg,
                team_drtg=away.drtg,
                injury_status=_injury_map(report, game.away, game.game_date),
            )
            context = build_game_context(
                game, context_schedule, analyzed_at=current.isoformat(), phase="FINAL"
            )
            projection, components = project_game(
                home=home,
                away=away,
                context=context,
                home_rotation=home_rotation,
                away_rotation=away_rotation,
            )
            input_manifest = build_input_manifest(
                context=context,
                home=home,
                away=away,
                home_rotation=home_rotation,
                away_rotation=away_rotation,
                stats_snapshot_sha256=str(pack["stat_pack_sha256"]),
                stats_observed_at=str(pack["observed_at"]),
                injury_snapshot_sha256=injury_snapshot["sha256"],
                injury_reported_at=str(report["reported_at"]),
            )
            entry_key = f"{game.game_id}|{GENERATION}|FINAL"
            eligible += 1
            if entry_key in seen:
                continue
            row = {
                "schema": "pulsar-nba-gamebook-provider-shadow-forecast-v1",
                "role": ROLE,
                "generation": GENERATION,
                "entry_key": entry_key,
                "game_id": game.game_id,
                "game_date": game.game_date,
                "home": game.home,
                "away": game.away,
                "forecast_at": current.isoformat(),
                "tipoff_at": game.commence_time,
                "source_snapshot_sha256": input_manifest["sha256"],
                "source_snapshot_at": input_manifest["source_snapshot_at"],
                "input_manifest": input_manifest,
                "gamebook_stat_pack_sha256": pack["stat_pack_sha256"],
                "gamebook_manifest_sha256": pack["gamebook_manifest_sha256"],
                "gamebook_completeness": completeness,
                "score_projection": asdict(projection),
                "home_ml": normal_cdf(projection.margin_mean / projection.margin_sd),
                "components": components,
                "limitations": list(pack.get("limitations") or []),
                "production_provider_authorized": False,
                "predictive_authority": False,
                "market_data_used": False,
                "promoted": False,
                "betting_certified": False,
            }
            append_jsonl(output, row)
            seen.add(entry_key)
            added += 1
        except Exception as exc:
            result["failures"].append(f"{game.game_id}:{type(exc).__name__}:{exc}")

    result.update({
        "candidate_games": eligible,
        "added": added,
        "gamebook_completeness": float(pack["gamebook_completeness"]),
        "gamebooks": int(pack.get("gamebooks") or 0),
        "teams_with_games": int(pack.get("teams_with_games") or 0),
        "status": (
            "SHADOW_FORECASTS_RECORDED"
            if added
            else "NO_NEW_SHADOW_FORECASTS"
            if eligible
            else "NO_ELIGIBLE_FINAL_WINDOW"
        ),
    })
    _status(status_output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record prospective gamebook-provider shadow forecasts"
    )
    eastern_today = datetime.now(
        ZoneInfo("America/New_York")
    ).date().isoformat()
    parser.add_argument("--date", default=eastern_today)
    parser.add_argument(
        "--output",
        default="runtime/provider_shadow/gamebook_forecasts.jsonl",
    )
    parser.add_argument(
        "--status",
        default="runtime/provider_shadow/status.json",
    )
    parser.add_argument("--max-network-games", type=int, default=60)
    args = parser.parse_args()
    result = run(
        target_date=args.date,
        output=args.output,
        status_output=args.status,
        max_network_games=args.max_network_games,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
