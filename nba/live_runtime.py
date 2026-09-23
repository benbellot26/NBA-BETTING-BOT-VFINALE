from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import MODEL_GENERATION, PROBABILITY_POLICY_ID
from .acquisition import fetch_nba_odds
from .data_quality import assess
from .injury_pdf import fetch_latest_report, game_report_ready
from .live_inputs import acquire_stat_pack, prior_day_cutoff, team_id, team_metric_from_pack
from .market import fresh_quote
from .odds_normalizer import normalize_game
from .pipeline import analyze_game
from .prospective import record_paper_candidates, record_final_forecasts
from .rotation_projection import normalized_player_name, project_rotation
from .schedule import fetch_schedule, games_on, season_for_date
from .schedule_context import build_game_context
from .snapshot_store import persist_snapshot
from .teams import canonical_team
from .timing import is_final_window


def _phase(minutes: float) -> str:
    if 5 <= minutes <= 30:
        return "FINAL"
    if minutes <= 180:
        return "PREGAME"
    if minutes <= 720:
        return "MORNING"
    return "EARLY"


def _minutes_to(commence: str, now: datetime) -> float:
    if not commence:
        return 9999.0
    dt = datetime.fromisoformat(commence.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("tip-off time lacks timezone")
    return (dt.astimezone(timezone.utc) - now).total_seconds() / 60.0


def _injury_map(report: dict[str, Any], team: str, game_date: str) -> dict[str, str]:
    return {
        str(row["player_name"]): str(row["status"])
        for row in report.get("records") or []
        if canonical_team(str(row.get("team") or "")) == canonical_team(team)
        and row.get("game_date") == game_date
    }


def _line(books: list[dict[str, Any]], selection: str) -> float | None:
    pinnacles = [book for book in books if str(book.get("bookmaker") or "").lower() == "pinnacle"]
    for book in pinnacles or books:
        for row in book.get("selections") or []:
            if row.get("selection") == selection and row.get("point") is not None:
                return float(row["point"])
    return None


def _same_tip(a: str, b: str) -> bool:
    try:
        ta = datetime.fromisoformat(a.replace("Z", "+00:00"))
        tb = datetime.fromisoformat(b.replace("Z", "+00:00"))
        if ta.tzinfo is None or tb.tzinfo is None:
            return False
        return abs((ta.astimezone(timezone.utc) - tb.astimezone(timezone.utc)).total_seconds()) <= 300
    except (ValueError, TypeError):
        return False


def _match(game: Any, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((
        row for row in rows
        if canonical_team(row["home"]) == canonical_team(game.home)
        and canonical_team(row["away"]) == canonical_team(game.away)
        and _same_tip(str(row.get("commence_time") or ""), game.commence_time)
    ), None)


def _load_cert(path: str) -> dict[str, Any]:
    """Only an explicitly approved source-controlled document may authorize BET.

    runtime-data/certification_candidate.json is evidence, never live authority.
    """
    default = {"certified": False, "markets": {}}
    try:
        cert = json.loads(Path(path).read_text(encoding="utf-8"))
        valid = (
            cert.get("certified") is True
            and cert.get("approved_for_live") is True
            and bool(cert.get("approved_at"))
            and cert.get("model_generation") == MODEL_GENERATION
            and cert.get("probability_policy_id") == PROBABILITY_POLICY_ID
        )
        return cert if valid else default
    except (OSError, ValueError, TypeError):
        return default


def _latest_quote(books: dict[str, list[dict[str, Any]]]) -> str | None:
    stamps = [book.get("last_update") for market in books.values() for book in market
              if book.get("last_update")]
    return max(stamps) if stamps else None


def _unmatched_injuries(
    report: dict[str, Any], team: str, game_date: str, rotation: list[Any],
) -> list[str]:
    projected = {normalized_player_name(row.name) for row in rotation}
    return [
        str(name) for name, status in _injury_map(report, team, game_date).items()
        if status.upper() in {"OUT", "DOUBTFUL", "QUESTIONABLE"}
        and normalized_player_name(name) not in projected
        and not any(
            str(row.get("reason") or "").lower().startswith("g league")
            for row in report.get("records") or []
            if row.get("game_date") == game_date
            and canonical_team(str(row.get("team") or "")) == canonical_team(team)
            and row.get("player_name") == name
        )
    ]


def run(
    *, target_date: str, output: str,
    snapshot_root: str = "runtime/snapshots",
    certification_path: str = "data/nba_betting_certification.json",
    paper_path: str = "runtime/evidence/paper_entries.jsonl",
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    observed = now.isoformat()
    season = season_for_date(target_date)
    out: dict[str, Any] = {
        "schema": "pulsar-nba-live-run-v2", "target_date": target_date,
        "season": season, "generated_at": observed, "status": "OK",
        "failures": [], "games": [],
    }
    try:
        schedule = fetch_schedule()
        slate = games_on(schedule, target_date)
    except Exception as exc:
        out["status"] = "NO_ANALYSIS"
        out["failures"].append(f"schedule:{exc}")
        schedule, slate = [], []

    if not slate:
        if out["status"] == "OK":
            out["status"] = "NO_GAMES"
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(out, indent=2), encoding="utf-8")
        return out

    try:
        odds = [normalize_game(item) for item in fetch_nba_odds()]
        persist_snapshot(snapshot_root, kind="odds", observed_at=observed,
                         payload=odds, source="the-odds-api")
    except Exception as exc:
        odds = []
        out["failures"].append(f"odds:{exc}")

    try:
        stats = acquire_stat_pack(season=season, game_date=target_date,
                                  observed_at=observed, snapshot_root=snapshot_root)
        if stats.get("date_to") != prior_day_cutoff(target_date):
            raise RuntimeError("stats PIT cutoff mismatch")
    except Exception as exc:
        stats = None
        out["failures"].append(f"stats:{exc}")

    try:
        injuries = fetch_latest_report(season=season)
        if not injuries.get("team_status"):
            raise RuntimeError("official injury PDF has no team submission rows")
        persist_snapshot(snapshot_root, kind="injuries",
                         observed_at=injuries["reported_at"],
                         payload=injuries, source=injuries["source_url"])
    except Exception as exc:
        injuries = None
        out["failures"].append(f"injuries:{exc}")

    cert = _load_cert(certification_path)
    if stats is not None and odds and injuries is not None:
        for game in slate:
            try:
                if not game_report_ready(injuries, game_date=game.game_date,
                                         home=game.home, away=game.away):
                    raise ValueError("game injury report not submitted for both teams")
                market = _match(game, odds)
                if market is None:
                    raise ValueError("odds event/team/tip time unmatched")
                spread = _line(market["markets"]["SPREAD"], "HOME")
                total = _line(market["markets"]["TOTAL"], "OVER")
                if spread is None or total is None:
                    raise ValueError("canonical spread/total line missing")
                freshness = assess(
                    analyzed_at=observed,
                    team_stats_at=stats["observed_at"],
                    injury_report_at=injuries["reported_at"],
                    odds_at=_latest_quote(market["markets"]),
                )
                if not freshness["eligible"]:
                    raise ValueError("PIT data-quality gate: " + ",".join(freshness["failures"]))
                phase = _phase(_minutes_to(game.commence_time, now))
                context = build_game_context(game, schedule, analyzed_at=observed, phase=phase)
                home = team_metric_from_pack(game.home, stats, home=True)
                away = team_metric_from_pack(game.away, stats, home=False)
                hr = project_rotation(
                    team_id(game.home), season_base=stats["player_season"],
                    recent_base=stats["player_recent"], season_advanced=stats["player_advanced"],
                    team_ortg=home.ortg, team_drtg=home.drtg,
                    injury_status=_injury_map(injuries, game.home, game.game_date),
                )
                ar = project_rotation(
                    team_id(game.away), season_base=stats["player_season"],
                    recent_base=stats["player_recent"], season_advanced=stats["player_advanced"],
                    team_ortg=away.ortg, team_drtg=away.drtg,
                    injury_status=_injury_map(injuries, game.away, game.game_date),
                )
                unmatched = (_unmatched_injuries(injuries, game.home, game.game_date, hr)
                             + _unmatched_injuries(injuries, game.away, game.game_date, ar))
                if unmatched:
                    raise ValueError("unmatched injury player(s): " + ", ".join(unmatched))
                key_lineup_unresolved = any(
                    row.status in {"QUESTIONABLE", "DOUBTFUL"} and row.minutes >= 24
                    for row in hr + ar
                )
                final = is_final_window(phase=phase, analyzed_at=observed,
                                        commence_time=game.commence_time)
                analysis = analyze_game(
                    home=home, away=away, context=context,
                    spread_line=spread, total_line=total, books_by_market=market["markets"],
                    certification=cert, home_rotation=hr, away_rotation=ar,
                    market_fresh=True, betting_window_ok=final,
                    lineup_uncertain=key_lineup_unresolved,
                )
                analysis["commence_time"] = game.commence_time
                analysis["injury_report_at"] = injuries["reported_at"]
                analysis["input_quality"] = freshness
                analysis["source_snapshot_sha256"] = stats["snapshot"]["sha256"]
                analysis["source_snapshot_at"] = stats["observed_at"]
                analysis["rotation_home"] = [asdict(row) for row in hr]
                analysis["rotation_away"] = [asdict(row) for row in ar]
                out["games"].append(analysis)
            except Exception as exc:
                out["failures"].append(f"{game.game_id}:{exc}")

    if not out["games"]:
        out["status"] = "NO_ANALYSIS"
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    out["paper_recording"] = record_paper_candidates(out, paper_path)
    out["final_forecasts"] = record_final_forecasts(out, "runtime/evidence/final_forecasts.jsonl")
    Path(output).write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(ZoneInfo("America/New_York")).date().isoformat())
    parser.add_argument("--output", default="runtime/live_run.json")
    parser.add_argument("--snapshot-root", default="runtime/snapshots")
    parser.add_argument("--certification", default="data/nba_betting_certification.json")
    parser.add_argument("--paper", default="runtime/evidence/paper_entries.jsonl")
    args = parser.parse_args()
    result = run(target_date=args.date, output=args.output, snapshot_root=args.snapshot_root,
                 certification_path=args.certification, paper_path=args.paper)
    print(json.dumps({"status": result["status"], "games": len(result["games"]),
                      "paper": result.get("paper_recording"), "failures": result["failures"]}, indent=2))


if __name__ == "__main__":
    main()
