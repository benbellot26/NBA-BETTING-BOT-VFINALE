from __future__ import annotations

from dataclasses import asdict
import math
from typing import Any, Iterable

from .decision import evaluate_candidate
from .distribution import probability_surface
from .market import best_execution, fresh_quote, paired_price_rows, pinnacle_no_vig
from .model import GameContext, TeamMetrics, prediction_payload
from .rotations import RotationPlayer
from .structural import project_game
from .uncertainty import intervals


def _settlement_supported(market: str, point: float | None) -> bool:
    if market == "ML":
        return point is None
    if point is None or not math.isfinite(float(point)):
        return False
    # The current continuous distribution does not assign push probability.
    return abs(abs(float(point)) % 1.0 - .5) < 1e-8


def _sharp_is_fresh(books: list[dict[str, Any]], left: str, right: str,
                    point: float | None, at: str) -> bool:
    return any(
        str(book.get("bookmaker") or "").lower() == "pinnacle"
        and paired_price_rows(book, left, right, point=point) is not None
        and fresh_quote(book.get("last_update"), at)
        for book in books
    )


def analyze_game(
    *, home: TeamMetrics, away: TeamMetrics, context: GameContext,
    spread_line: float, total_line: float,
    books_by_market: dict[str, list[dict[str, Any]]] | None = None,
    certification: dict[str, Any] | None = None,
    home_rotation: Iterable[RotationPlayer] | None = None,
    away_rotation: Iterable[RotationPlayer] | None = None,
    market_fresh: bool = True, betting_window_ok: bool = False,\n    lineup_uncertain: bool = False,
) -> dict[str, Any]:
    projection, components = project_game(home=home, away=away, context=context,
                                           home_rotation=home_rotation, away_rotation=away_rotation)
    surface = probability_surface(projection, spread_line=spread_line, total_line=total_line)
    payload = prediction_payload(projection, surface, components=components)
    probabilities = asdict(surface)
    unresolved = projection.data_quality == "LINEUP_UNCERTAIN" or lineup_uncertain
    bands = intervals(probabilities, data_quality="LINEUP_UNCERTAIN" if unresolved else projection.data_quality,
                      market_fresh=market_fresh, unresolved_key_player=unresolved)
    payload["probability_intervals"] = bands
    payload["decision"] = {"candidates": []}
    if not books_by_market:
        return payload
    cert = certification or {"certified": False, "markets": {}}
    specs = [
        ("home_ml", "ML", "HOME", "AWAY", None),
        ("away_ml", "ML", "AWAY", "HOME", None),
        ("home_spread", "SPREAD", "HOME", "AWAY", spread_line),
        ("away_spread", "SPREAD", "AWAY", "HOME", -spread_line),
        ("over", "TOTAL", "OVER", "UNDER", total_line),
        ("under", "TOTAL", "UNDER", "OVER", total_line),
    ]
    for key, market, left, right, point in specs:
        books = books_by_market.get(market) or []
        execution = best_execution(books, left, point=point)
        if execution is None:
            continue
        sharp = pinnacle_no_vig(books, left, right, point=point)
        sharp_probability = sharp.get(left) if sharp else None
        fresh = (
            market_fresh and fresh_quote(execution.get("last_update"), context.analyzed_at)
            and _sharp_is_fresh(books, left, right, point, context.analyzed_at)
        )
        mcert = bool(cert.get("certified") is True and
                     ((cert.get("markets") or {}).get(market) or {}).get("betting_certified") is True)
        candidate = evaluate_candidate(
            selection=key, market=market, model_probability=float(probabilities[key]),
            lower_probability=float(bands["selections"][key]["lower"]),
            price=float(execution["price"]), sharp_probability=sharp_probability,
            certified=mcert, market_fresh=fresh, lineup_unresolved=unresolved,
            timing_eligible=betting_window_ok, contract_supported=_settlement_supported(market, point),
        )
        candidate.update({
            "execution_book": execution.get("bookmaker"), "game_id": context.game_id,
            "line": point, "execution_last_update": execution.get("last_update"),
        })
        payload["decision"]["candidates"].append(candidate)
    return payload
