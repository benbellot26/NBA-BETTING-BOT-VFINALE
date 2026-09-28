"""Trusted postgame outcome adapter over cached NBA Official Scorer gamebooks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .gamebook_stats import _validate_cached
from .schedule import ScheduleGame

SOURCE = "official_nba_gamebook"
STATUS_TEXT = "Final - NBA Official Scorer's Report"


def cached_gamebook_finals(
    cache_root: str | Path = "runtime/gamebook_reference",
) -> dict[str, ScheduleGame]:
    """Return validated official finals already persisted by gamebook collection.

    This is postgame-only authority. It never creates predictive inputs and it
    never fetches the network itself.
    """
    root = Path(cache_root) / "gamebooks"
    if not root.exists():
        return {}
    finals: dict[str, ScheduleGame] = {}
    identities: set[tuple[str, str, str]] = set()
    for path in sorted(root.glob("*.json")):
        try:
            payload = _validate_cached(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"invalid cached official gamebook {path.name}: {type(exc).__name__}"
            ) from None
        reference_id = str(payload["reference_id"])
        game_date = str(payload["game_date"])
        home = str(payload["home"])
        away = str(payload["away"])
        parsed = payload["parsed"]
        home_score = int(parsed["home_score"])
        away_score = int(parsed["away_score"])
        if min(home_score, away_score) < 0:
            raise ValueError("negative gamebook final score")
        identity = (game_date, home, away)
        if reference_id in finals:
            raise ValueError(f"duplicate gamebook reference id: {reference_id}")
        if identity in identities:
            raise ValueError(
                f"duplicate gamebook date/team outcome identity: {identity}"
            )
        identities.add(identity)
        finals[reference_id] = ScheduleGame(
            game_id=reference_id,
            game_date=game_date,
            # The cache's authority is score/date/teams. Commence time is not
            # reconstructed after the fact and is intentionally left blank.
            commence_time="",
            home=home,
            away=away,
            status=3,
            status_text=STATUS_TEXT,
            home_score=home_score,
            away_score=away_score,
        )
    return finals


def is_gamebook_final(game: Any) -> bool:
    return (
        isinstance(game, ScheduleGame)
        and game.final
        and str(game.status_text) == STATUS_TEXT
        and game.home_score is not None
        and game.away_score is not None
    )
