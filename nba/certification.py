"""Necessary prospective gates; never a substitute for explicit live approval."""
from __future__ import annotations

import math
from typing import Any

MIN_GAMES = 600
MIN_MARKET_N = 400
MIN_FULL_COHORT_N = 400
MAX_ECE = .05
MIN_PAIRED_SHARP_N = 400
MIN_CLV_N = 100
MIN_POSITIVE_CLV_RATE = .52
MARKETS = ("ML", "SPREAD", "TOTAL")


def _integer(record: dict[str, Any], key: str) -> int:
    try:
        value = float(record[key])
        return int(value) if value.is_integer() and value >= 0 else -1
    except (ValueError, TypeError, KeyError, OverflowError):
        return -1


def _rate(record: dict[str, Any], key: str) -> float:
    try:
        value = float(record[key])
        return value if math.isfinite(value) and 0 <= value <= 1 else math.inf
    except (ValueError, TypeError, KeyError):
        return math.inf


def certify(evidence: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if evidence.get("audit_ok") is not True:
        failures.append("prospective_evidence_audit_not_passed")
    if _integer(evidence, "games") < MIN_GAMES:
        failures.append(f"games<{MIN_GAMES}")
    markets = evidence.get("markets") or {}
    market_state: dict[str, Any] = {}
    for market in MARKETS:
        current = markets.get(market) or {}
        errors = []
        if _integer(current, "n") < MIN_MARKET_N:
            errors.append(f"n<{MIN_MARKET_N}")
        if _rate(current, "ece") > MAX_ECE:
            errors.append(f"ece>{MAX_ECE}")
        if _integer(current, "full_cohort_n") < MIN_FULL_COHORT_N:
            errors.append(f"full_cohort_n<{MIN_FULL_COHORT_N}")
        if _rate(current, "full_cohort_ece") > MAX_ECE:
            errors.append(f"full_cohort_ece>{MAX_ECE}")
        if _integer(current, "paired_sharp_n") < MIN_PAIRED_SHARP_N:
            errors.append(f"paired_sharp_n<{MIN_PAIRED_SHARP_N}")
        if _integer(current, "clv_n") < MIN_CLV_N:
            errors.append(f"clv_n<{MIN_CLV_N}")
        if not math.isfinite(_rate(current, "positive_clv_rate")) or _rate(current, "positive_clv_rate") < MIN_POSITIVE_CLV_RATE:
            errors.append(f"positive_clv_rate<{MIN_POSITIVE_CLV_RATE}")
        market_state[market] = {
            "betting_certified": not errors and not failures, "failures": errors,
        }
        failures.extend(f"{market}:{error}" for error in errors)
    # A candidate may earn statistical gates, but live permission always
    # requires separate source-controlled signed-off approval in live_runtime.
    if failures:
        for value in market_state.values():
            value["betting_certified"] = False
    return {
        "certified": not failures, "markets": market_state,
        "failures": failures, "approved_for_live": False,
        "role": "RESEARCH_CERTIFICATION_CANDIDATE",
    }
