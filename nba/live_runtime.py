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
from .injury_pdf import game_report_ready
from .live_inputs import prior_day_cutoff, team_id, team_metric_from_pack
from .lineage import build_input_manifest
from .market import fresh_quote
from .odds_normalizer import normalize_game
from .odds_budget import reserve as reserve_odds_request
from .pipeline import analyze_game
from .provider_contract import NoGamesOnTargetDate
from .providers import OfficialNBAProvider
from .prospective import record_paper_candidates, record_final_forecasts
from .rotation_projection import normalized_player_name, project_rotation
from .schedule import ScheduleGame, games_on, season_for_date
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
    forecasts_path: str = "runtime/evidence/final_forecasts.jsonl",
    odds_budget_path: str = "runtime/odds_budget.json",
    operating_mode: str = "regular",
) -> dict[str, Any]:
    if operating_mode not in {"regular", "preseason"}:
        raise ValueError("operating_mode must be regular or preseason")
    started_at = datetime.now(timezone.utc).isoformat()
    season = season_for_date(target_date)
    out: dict[str, Any] = {
        "schema": "pulsar-nba-live-run-v3", "target_date": target_date,
        "season": season, "generated_at": started_at, "status": "OK",
        "source_provider": "official-nba", "failures": [], "games": [],
        "odds_api_requests": 0, "operating_mode": operating_mode,
        "prospective_evidence_eligible": operating_mode == "regular",
    }
    # The live path always constructs its OWN official provider. JSON files,
    # local bundles and CI fixtures have no route to live/paper certification.
    try:
        source = OfficialNBAProvider(snapshot_root=snapshot_root).capture(
            target_date=target_date)
        if source.provider_id != "official-nba" or source.role != "PROSPECTIVE_SOURCE":
            raise ValueError("untrusted source refused by live runtime")
        source.validated()
        schedule = [ScheduleGame(**row) for row in source.schedule]
        stats = source.stats
        injuries = source.injuries
        if not injuries.get("team_status"):
            raise ValueError("official injury report has no submission rows")
        if stats.get("date_to") != prior_day_cutoff(target_date):
            raise ValueError("stats PIT cutoff mismatch")
        injury_snapshot = persist_snapshot(
            snapshot_root, kind="injuries", observed_at=injuries["reported_at"],
            payload=injuries, source=injuries.get("source_url") or "official-nba")
    except NoGamesOnTargetDate:
        out["status"] = "NO_GAMES"
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(out, indent=2), encoding="utf-8")
        return out
    except Exception as exc:
        out["status"] = "NO_ANALYSIS"
        out["failures"].append(f"official_provider:{exc}")
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(out, indent=2), encoding="utf-8")
        return out

    source_time = datetime.fromisoformat(source.captured_at.replace("Z", "+00:00"))
    slate = [game for game in games_on(schedule, target_date)
             if _minutes_to(game.commence_time, source_time) > 0]
    if not slate:
        out["status"] = "NO_GAMES"
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(out, indent=2), encoding="utf-8")
        return out

    # Pre-check source freshness WITHOUT calling the paid Odds API. The
    # placeholder odds_at is only for this source-only gate, not a market quote.
    source_quality = assess(
        analyzed_at=source.captured_at, team_stats_at=stats["observed_at"],
        injury_report_at=injuries["reported_at"], odds_at=source.captured_at)
    eligible_games = [
        game for game in slate if game_report_ready(
            injuries, game_date=game.game_date, home=game.home, away=game.away)
    ]
    if not source_quality["eligible"] or not eligible_games:
        out["status"] = "NO_ANALYSIS"
        out["failures"].append("odds_skipped:mandatory_source_unavailable_or_stale")
        out["source_quality"] = source_quality
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(out, indent=2), encoding="utf-8")
        return out

    # For regular-season research, refuse a paid market request when no
    # upcoming game clears the minimum completed-game sample. The preseason
    # plumbing mode may still exercise the market path with sparse samples.
    if operating_mode == "regular":
        team_rows = (stats.get("advanced_windows") or {}).get(0) or (
            stats.get("advanced_windows") or {}).get("0") or []
        games_played = {
            canonical_team(str(row.get("TEAM_NAME") or "")): int(row.get("GP") or 0)
            for row in team_rows
        }
        if not any(min(games_played.get(game.home, 0),
                       games_played.get(game.away, 0)) >= 5
                   for game in eligible_games):
            out["status"] = "NO_ANALYSIS"
            out["failures"].append(
                "odds_skipped:all_upcoming_games_below_five_completed_team_games")
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_text(json.dumps(out, indent=2), encoding="utf-8")
            return out

    try:
        reserve_odds_request(path=odds_budget_path, purpose="live_analysis")
        out["odds_api_requests"] += 1
        odds = [normalize_game(item) for item in fetch_nba_odds()]
        # Analysis time is AFTER quote acquisition, never the earlier start
        # of a slow source request. The FINAL gate uses this later timestamp.
        now = datetime.now(timezone.utc)
        observed = now.isoformat()
        out["generated_at"] = observed
        persist_snapshot(snapshot_root, kind="odds", observed_at=observed,
                         payload=odds, source="the-odds-api")
    except Exception as exc:
        odds = []
        out["failures"].append(f"odds:{exc}")
        now = datetime.now(timezone.utc)
        observed = now.isoformat()
        out["generated_at"] = observed

    cert = (_load_cert(certification_path) if operating_mode == "regular"
            else {"certified": False, "markets": {}})
    if stats is not None and odds and injuries is not None:
        for game in slate:
            try:
                if _minutes_to(game.commence_time, now) <= 0:
                    raise ValueError("tipoff already passed before odds acquisition completed")
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
                team_rows = stats["advanced_windows"].get(0) or stats["advanced_windows"].get("0") or []
                gp = {canonical_team(str(row.get("TEAM_NAME") or "")): int(row.get("GP") or 0)
                      for row in team_rows}
                minimum_games = 5 if operating_mode == "regular" else 0
                if min(gp.get(game.home, 0), gp.get(game.away, 0)) < minimum_games:
                    raise ValueError(f"early-season sample below {minimum_games} completed team games")
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
                input_manifest = build_input_manifest(
                    context=context, home=home, away=away,
                    home_rotation=hr, away_rotation=ar,
                    stats_snapshot_sha256=stats["snapshot"]["sha256"],
                    stats_observed_at=stats["observed_at"],
                    injury_snapshot_sha256=injury_snapshot["sha256"],
                    injury_reported_at=injuries["reported_at"],
                )
                analysis["input_manifest"] = input_manifest
                analysis["source_snapshot_sha256"] = input_manifest["sha256"]
                analysis["source_snapshot_at"] = input_manifest["source_snapshot_at"]
                analysis["rotation_home"] = [asdict(row) for row in hr]
                analysis["rotation_away"] = [asdict(row) for row in ar]
                out["games"].append(analysis)
            except Exception as exc:
                out["failures"].append(f"{game.game_id}:{exc}")

    if not out["games"]:
        out["status"] = "NO_ANALYSIS"
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    if operating_mode == "regular":
        out["paper_recording"] = record_paper_candidates(out, paper_path)
        out["final_forecasts"] = record_final_forecasts(out, forecasts_path)
    else:
        out["paper_recording"] = {"added": 0, "reason": "preseason_not_evidence"}
        out["final_forecasts"] = {"added": 0, "reason": "preseason_not_evidence"}
    Path(output).write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(ZoneInfo("America/New_York")).date().isoformat())
    parser.add_argument("--output", default="runtime/live_run.json")
    parser.add_argument("--snapshot-root", default="runtime/snapshots")
    parser.add_argument("--certification", default="data/nba_betting_certification.json")
    parser.add_argument("--paper", default="runtime/evidence/paper_entries.jsonl")
    parser.add_argument("--mode", choices=("regular","preseason"), default="regular")
    args = parser.parse_args()
    result = run(target_date=args.date, output=args.output, snapshot_root=args.snapshot_root,
                 certification_path=args.certification, paper_path=args.paper,
                 operating_mode=args.mode)
    print(json.dumps({"status": result["status"], "games": len(result["games"]),
                      "paper": result.get("paper_recording"), "failures": result["failures"]}, indent=2))


if __name__ == "__main__":
    main()
