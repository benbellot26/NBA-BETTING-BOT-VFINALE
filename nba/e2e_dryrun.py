"""Network-free end-to-end CI proof of the basketball analysis chain."""
from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any

from .fixture_provider import DeterministicFixtureProvider
from .injury_pdf import game_report_ready
from .lineage import build_input_manifest
from .live_inputs import team_id, team_metric_from_pack
from .model import ProbabilitySurface
from .pipeline import analyze_game
from .rotation_projection import project_rotation
from .schedule import ScheduleGame
from .schedule_context import build_game_context
from .snapshot_store import canonical_bytes
import hashlib


def _fixture_books(at: str) -> dict[str, list[dict[str, Any]]]:
    return {
        "ML": [{
            "bookmaker": "pinnacle", "last_update": at,
            "selections": [
                {"selection": "HOME", "price": 1.91},
                {"selection": "AWAY", "price": 1.99},
            ],
        }],
        "SPREAD": [{
            "bookmaker": "pinnacle", "last_update": at,
            "selections": [
                {"selection": "HOME", "price": 1.91, "point": -3.5},
                {"selection": "AWAY", "price": 1.91, "point": 3.5},
            ],
        }],
        "TOTAL": [{
            "bookmaker": "pinnacle", "last_update": at,
            "selections": [
                {"selection": "OVER", "price": 1.91, "point": 226.5},
                {"selection": "UNDER", "price": 1.91, "point": 226.5},
            ],
        }],
    }


def run() -> dict[str, Any]:
    snapshot = DeterministicFixtureProvider().capture(target_date="2026-11-15")
    games = [ScheduleGame(**row) for row in snapshot.schedule]
    game = games[0]
    if not game_report_ready(snapshot.injuries, game_date=game.game_date,
                             home=game.home, away=game.away):
        raise RuntimeError("fixture injury submission failed")
    home = team_metric_from_pack(game.home, snapshot.stats, home=True)
    away = team_metric_from_pack(game.away, snapshot.stats, home=False)
    context = build_game_context(
        game, games, analyzed_at=snapshot.captured_at, phase="FINAL")
    home_rotation = project_rotation(
        team_id(game.home),
        season_base=snapshot.stats["player_season"],
        recent_base=snapshot.stats["player_recent"],
        season_advanced=snapshot.stats["player_advanced"],
        team_ortg=home.ortg, team_drtg=home.drtg,
    )
    away_rotation = project_rotation(
        team_id(game.away),
        season_base=snapshot.stats["player_season"],
        recent_base=snapshot.stats["player_recent"],
        season_advanced=snapshot.stats["player_advanced"],
        team_ortg=away.ortg, team_drtg=away.drtg,
    )
    books = _fixture_books(snapshot.captured_at)
    analysis = analyze_game(
        home=home, away=away, context=context,
        spread_line=-3.5, total_line=226.5,
        books_by_market=books,
        certification={"certified": False, "markets": {}},
        home_rotation=home_rotation, away_rotation=away_rotation,
        market_fresh=True, betting_window_ok=True,
    )
    injury_hash = hashlib.sha256(canonical_bytes(snapshot.injuries)).hexdigest()
    manifest = build_input_manifest(
        context=context, home=home, away=away,
        home_rotation=home_rotation, away_rotation=away_rotation,
        stats_snapshot_sha256=snapshot.stats["snapshot"]["sha256"],
        stats_observed_at=snapshot.stats["observed_at"],
        injury_snapshot_sha256=injury_hash,
        injury_reported_at=snapshot.injuries["reported_at"],
    )
    surface = ProbabilitySurface(**analysis["probabilities"]).validated()
    candidates = analysis["decision"]["candidates"]
    if not candidates:
        raise RuntimeError("dry-run generated no market candidates")
    if any(candidate["status"] == "BET" for candidate in candidates):
        raise RuntimeError("uncertified dry-run unexpectedly authorized BET")
    return {
        "schema": "pulsar-nba-e2e-dryrun-v1",
        "role": "SYNTHETIC_CI_ONLY",
        "provider_fingerprint": snapshot.fingerprint(),
        "input_manifest_sha256": manifest["sha256"],
        "game_id": game.game_id,
        "projected_score": analysis["score_projection"],
        "probabilities": asdict(surface),
        "candidate_count": len(candidates),
        "bet_count": sum(candidate["status"] == "BET" for candidate in candidates),
        "all_probabilities_valid": True,
        "rotations_240": (
            abs(sum(row.minutes for row in home_rotation) - 240) < 1e-9
            and abs(sum(row.minutes for row in away_rotation) - 240) < 1e-9
        ),
    }


def main() -> None:
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["bet_count"] != 0 or not result["rotations_240"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
