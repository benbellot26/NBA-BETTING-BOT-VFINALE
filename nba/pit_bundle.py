"""Locally captured NBA inputs for OFFLINE RESEARCH ONLY.

GitHub-hosted runners currently cannot reach all required NBA endpoints.
A locally collected bundle can exercise the basketball model without treating
an unverified upload as prospective evidence or authorizing any bet.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .injury_pdf import fetch_latest_report, game_report_ready
from .live_inputs import acquire_stat_pack, prior_day_cutoff, team_id, team_metric_from_pack
from .live_runtime import _injury_map, _unmatched_injuries
from .model import GameContext
from .pipeline import analyze_game
from .rotation_projection import project_rotation
from .schedule import ScheduleGame, fetch_schedule, games_on, season_for_date
from .schedule_context import build_game_context
from .structural import project_game
from .stat_contract import validate_game_stat_pack

SCHEMA = "pulsar-nba-offline-input-bundle-v1"
ROLE = "UNVERIFIED_OFFLINE_RESEARCH"


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("PIT timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _digest(row: dict[str, Any]) -> str:
    payload = {key: value for key, value in row.items() if key != "sha256"}
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def pack(
    *, target_date: str, season: str, captured_at: str,
    schedule: list[ScheduleGame], stats: dict[str, Any],
    injuries: dict[str, Any],
) -> dict[str, Any]:
    bundle = {
        "schema": SCHEMA, "role": ROLE,
        "target_date": target_date, "season": season, "captured_at": captured_at,
        "schedule": [asdict(game) for game in schedule],
        "stats": stats, "injuries": injuries,
    }
    bundle["sha256"] = _digest(bundle)
    return validate(bundle)


def validate(bundle: dict[str, Any]) -> dict[str, Any]:
    if bundle.get("schema") != SCHEMA or bundle.get("role") != ROLE:
        raise ValueError("unsupported or potentially live-authorized bundle")
    if bundle.get("sha256") != _digest(bundle):
        raise ValueError("offline bundle checksum mismatch")
    captured = _dt(str(bundle["captured_at"]))
    date = str(bundle["target_date"])
    if bundle["season"] != season_for_date(date):
        raise ValueError("bundle season mismatch")
    stats = bundle["stats"]
    if stats.get("season") != bundle["season"]:
        raise ValueError("stat-pack season mismatch")
    if stats.get("date_to") != prior_day_cutoff(date):
        raise ValueError("stat-pack PIT date cutoff mismatch")
    if _dt(str(stats["observed_at"])) > captured:
        raise ValueError("statistics were observed after bundle capture")
    report = bundle["injuries"]
    if _dt(str(report["reported_at"])) > captured:
        raise ValueError("injury report was issued after bundle capture")
    games = [ScheduleGame(**row) for row in bundle["schedule"]]
    slate = games_on(games, date)
    if not slate:
        raise ValueError("offline bundle has no NBA games on target date")
    if any(_dt(game.commence_time) <= captured for game in slate):
        raise ValueError("offline bundle must be captured before every target tip-off")
    for game in slate:
        validate_game_stat_pack(
            stats, game.home, game.away, min_team_games=5,
            strict_live=False)
    return bundle


def save(bundle: dict[str, Any], output: str | Path) -> None:
    validate(bundle)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(bundle, sort_keys=True, indent=2), encoding="utf-8")


def load(path: str | Path) -> dict[str, Any]:
    return validate(json.loads(Path(path).read_text(encoding="utf-8")))


def collect_local(*, target_date: str, output: str | Path) -> dict[str, Any]:
    """Fetch with the *local machine's network*. No odds credentials are needed."""
    observed = datetime.now(timezone.utc).isoformat()
    season = season_for_date(target_date)
    schedule = fetch_schedule()
    slate = games_on(schedule, target_date)
    if not slate:
        raise RuntimeError("no NBA games for target date")
    stats = acquire_stat_pack(
        season=season, observed_at=observed, game_date=target_date,
        snapshot_root=str(Path(output).parent / "nba_local_snapshots"),
    )
    report = fetch_latest_report(season=season)
    if not all(game_report_ready(report, game_date=game.game_date,
                                 home=game.home, away=game.away) for game in slate):
        raise RuntimeError("official injury report was not submitted for every target team")
    bundle = pack(target_date=target_date, season=season, captured_at=datetime.now(timezone.utc).isoformat(),
                  schedule=schedule, stats=stats, injuries=report)
    save(bundle, output)
    return {"status": ROLE, "games": len(slate), "sha256": bundle["sha256"], "output": str(output)}


def analyze_offline(bundle: dict[str, Any],
                    lines: dict[str, dict[str, float]] | None = None) -> dict[str, Any]:
    """Research results only; never returns authorized BET/paper records."""
    data = validate(bundle)
    games = [ScheduleGame(**row) for row in data["schedule"]]
    slate = games_on(games, data["target_date"])
    report = data["injuries"]
    stats = data["stats"]
    output: dict[str, Any] = {
        "schema": "pulsar-nba-offline-analysis-v1", "role": ROLE,
        "bundle_sha256": data["sha256"], "betting_certified": False,
        "prospective_certification_eligible": False,
        "paper_eligible": False, "games": [], "failures": [],
    }
    for game in slate:
        try:
            if not game_report_ready(report, game_date=game.game_date,
                                     home=game.home, away=game.away):
                raise ValueError("required official injury submission absent")
            home = team_metric_from_pack(game.home, stats, home=True)
            away = team_metric_from_pack(game.away, stats, home=False)
            context = build_game_context(game, games, analyzed_at=data["captured_at"], phase="RESEARCH")
            hr = project_rotation(team_id(game.home), season_base=stats["player_season"],
                                  recent_base=stats["player_recent"],
                                  season_advanced=stats["player_advanced"],
                                  team_ortg=home.ortg, team_drtg=home.drtg,
                                  injury_status=_injury_map(report, game.home, game.game_date))
            ar = project_rotation(team_id(game.away), season_base=stats["player_season"],
                                  recent_base=stats["player_recent"],
                                  season_advanced=stats["player_advanced"],
                                  team_ortg=away.ortg, team_drtg=away.drtg,
                                  injury_status=_injury_map(report, game.away, game.game_date))
            unmatched = (_unmatched_injuries(report, game.home, game.game_date, hr)
                         + _unmatched_injuries(report, game.away, game.game_date, ar))
            if unmatched:
                raise ValueError("unmatched key injury: " + ", ".join(unmatched))
            row = (lines or {}).get(game.game_id)
            if row is None:
                projection, components = project_game(
                    home=home, away=away, context=context,
                    home_rotation=hr, away_rotation=ar)
                result = {"game_id": game.game_id, "score_projection": asdict(projection),
                          "components": components, "probabilities": None,
                          "note": "No market lines supplied; only score/margin/total are projected."}
            else:
                result = analyze_game(
                    home=home, away=away, context=context,
                    spread_line=float(row["spread_line"]), total_line=float(row["total_line"]),
                    home_rotation=hr, away_rotation=ar, market_fresh=False,
                    betting_window_ok=False, certification={"certified": False, "markets": {}})
                result["note"] = "Imported files are unverified research. No wager authorization."
            result["role"] = ROLE
            result["betting_certified"] = False
            output["games"].append(result)
        except Exception as exc:
            output["failures"].append({"game_id": game.game_id, "reason": str(exc)})
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline NBA PIT bundle; RESEARCH ONLY")
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect")
    collect.add_argument("--date", required=True)
    collect.add_argument("--output", required=True)
    research = commands.add_parser("analyze")
    research.add_argument("--input", required=True)
    research.add_argument("--lines", help="Optional JSON mapping game_id -> spread_line/total_line")
    research.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "collect":
        print(json.dumps(collect_local(target_date=args.date, output=args.output), indent=2))
    else:
        line_map = json.loads(Path(args.lines).read_text(encoding="utf-8")) if args.lines else None
        result = analyze_offline(load(args.input), line_map)
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, sort_keys=True, indent=2), encoding="utf-8")
        print(json.dumps({"role": result["role"], "games": len(result["games"]),
                          "failures": result["failures"], "output": str(target)}, indent=2))


if __name__ == "__main__":
    main()
