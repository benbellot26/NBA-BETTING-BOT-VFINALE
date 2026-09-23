from __future__ import annotations

from typing import Any

BASE_HALF_WIDTH = {"ML": .060, "SPREAD": .070, "TOTAL": .080}


def intervals(probabilities: dict[str, float], *, data_quality: str = "GOOD", market_fresh: bool = True, unresolved_key_player: bool = False) -> dict[str, Any]:
    penalty = 0.0
    reasons: list[str] = []
    if data_quality != "GOOD":
        penalty += .020; reasons.append("data_quality")
    if not market_fresh:
        penalty += .015; reasons.append("market_freshness")
    if unresolved_key_player:
        penalty += .025; reasons.append("key_player_unresolved")
    mapping = {
        "home_ml": "ML", "away_ml": "ML",
        "home_spread": "SPREAD", "away_spread": "SPREAD",
        "over": "TOTAL", "under": "TOTAL",
    }
    out = {}
    for key, market in mapping.items():
        if key not in probabilities:
            continue
        p = float(probabilities[key]); half = min(.18, BASE_HALF_WIDTH[market] + penalty)
        out[key] = {"lower": max(0.0, p-half), "upper": min(1.0, p+half), "half_width_pp": half*100, "basis": "CONSERVATIVE_FALLBACK"}
    return {"selections": out, "penalty_pp": penalty*100, "penalty_reasons": reasons}
