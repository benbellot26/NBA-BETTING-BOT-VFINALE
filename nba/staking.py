from __future__ import annotations

from typing import Any

KELLY_FRACTION = .25
MAX_BET_BANKROLL_FRACTION = .010
MAX_GAME_BANKROLL_FRACTION = .015
MAX_DAILY_BANKROLL_FRACTION = .030
MAX_MARKET_BANKROLL_FRACTION = .020


def full_kelly(probability: float, decimal_odds: float) -> float:
    b = decimal_odds - 1.0
    if not 0 < probability < 1 or b <= 0:
        return 0.0
    return max(0.0, (b*probability - (1-probability))/b)


def conservative_stake_fraction(candidate: dict[str, Any], *, certified: bool) -> float:
    if not certified or candidate.get("status") != "BET":
        return 0.0
    p = float(candidate["lower_probability"]); odds = float(candidate["price"])
    return min(MAX_BET_BANKROLL_FRACTION, KELLY_FRACTION*full_kelly(p, odds))


def size_portfolio(candidates: list[dict[str, Any]], *, certified: bool) -> list[dict[str, Any]]:
    daily = 0.0; by_game: dict[str, float] = {}; by_market: dict[str, float] = {}; out = []
    ranked = sorted(candidates, key=lambda r: float(r.get("robust_edge_pp") or -999), reverse=True)
    for row in ranked:
        f = conservative_stake_fraction(row, certified=certified)
        game = str(row.get("game_id") or "UNKNOWN"); market = str(row.get("market") or "UNKNOWN")
        f = min(f, max(0.0, MAX_DAILY_BANKROLL_FRACTION-daily), max(0.0, MAX_GAME_BANKROLL_FRACTION-by_game.get(game,0.0)), max(0.0, MAX_MARKET_BANKROLL_FRACTION-by_market.get(market,0.0)))
        enriched = dict(row); enriched["stake_fraction"] = f; out.append(enriched)
        daily += f; by_game[game] = by_game.get(game,0.0)+f; by_market[market] = by_market.get(market,0.0)+f
    return out
