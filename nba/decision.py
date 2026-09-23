from __future__ import annotations
from typing import Any

BASE_EDGE_PP = {"ML": 3.0, "SPREAD": 3.5, "TOTAL": 4.0}
BASE_ROBUST_EDGE_PP = {"ML": 1.5, "SPREAD": 2.0, "TOTAL": 2.5}
MIN_ROBUST_SHARP_EDGE_PP = {"ML": .25, "SPREAD": .50, "TOTAL": .75}


def evaluate_candidate(
    *, selection: str, market: str, model_probability: float, lower_probability: float,
    price: float, sharp_probability: float | None, certified: bool, market_fresh: bool,
    lineup_unresolved: bool = False, timing_eligible: bool = True,
    contract_supported: bool = True,
) -> dict[str, Any]:
    breakeven = 1.0 / float(price)
    model_edge = 100 * (model_probability - breakeven)
    robust_edge = 100 * (lower_probability - breakeven)
    sharp_edge = None if sharp_probability is None else 100 * (model_probability - sharp_probability)
    robust_sharp_edge = None if sharp_probability is None else 100 * (lower_probability - sharp_probability)
    operational = []
    if not timing_eligible:
        operational.append("outside_certified_final_window")
    if not market_fresh:
        operational.append("market_not_fresh")
    if not contract_supported:
        operational.append("whole_point_push_not_modeled")
    if lineup_unresolved:
        operational.append("key_player_unresolved")
    if model_edge < BASE_EDGE_PP[market]:
        operational.append("model_edge_below_threshold")
    if robust_edge < BASE_ROBUST_EDGE_PP[market]:
        operational.append("robust_edge_below_threshold")
    if sharp_probability is None:
        operational.append("pinnacle_no_vig_missing")
    elif robust_sharp_edge is None or robust_sharp_edge < MIN_ROBUST_SHARP_EDGE_PP[market]:
        operational.append("robust_sharp_edge_below_threshold")
    failures = (["market_not_certified"] if not certified else []) + operational
    paper_eligible = not operational
    return {
        "selection": selection, "market": market,
        "status": "BET" if certified and paper_eligible else "NO_BET",
        "research_ready": paper_eligible, "paper_eligible": paper_eligible,
        "edge_qualified": (
            model_edge >= BASE_EDGE_PP[market] and robust_edge >= BASE_ROBUST_EDGE_PP[market]
            and sharp_probability is not None and robust_sharp_edge is not None
            and robust_sharp_edge >= MIN_ROBUST_SHARP_EDGE_PP[market]
        ),
        "model_probability": model_probability, "lower_probability": lower_probability,
        "price": price, "breakeven_probability": breakeven,
        "model_edge_pp": model_edge, "robust_edge_pp": robust_edge,
        "sharp_probability": sharp_probability, "sharp_edge_pp": sharp_edge,
        "robust_sharp_edge_pp": robust_sharp_edge, "failures": failures,
    }
