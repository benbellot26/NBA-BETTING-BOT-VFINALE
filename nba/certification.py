from __future__ import annotations

from typing import Any

MIN_GAMES = 600
MIN_MARKET_N = 400
MAX_ECE = .05
MIN_PAIRED_SHARP_N = 400
MIN_CLV_N = 100
MIN_POSITIVE_CLV_RATE = .52
MARKETS = ("ML", "SPREAD", "TOTAL")


def certify(evidence: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if int(evidence.get("games") or 0) < MIN_GAMES: failures.append(f"games<{MIN_GAMES}")
    markets = evidence.get("markets") or {}
    market_state: dict[str, Any] = {}
    for market in MARKETS:
        m = markets.get(market) or {}; f=[]
        if int(m.get("n") or 0) < MIN_MARKET_N: f.append(f"n<{MIN_MARKET_N}")
        if float(m.get("ece") or 1.0) > MAX_ECE: f.append(f"ece>{MAX_ECE}")
        if int(m.get("paired_sharp_n") or 0) < MIN_PAIRED_SHARP_N: f.append(f"paired_sharp_n<{MIN_PAIRED_SHARP_N}")
        if int(m.get("clv_n") or 0) < MIN_CLV_N: f.append(f"clv_n<{MIN_CLV_N}")
        if float(m.get("positive_clv_rate") or 0.0) < MIN_POSITIVE_CLV_RATE: f.append(f"positive_clv_rate<{MIN_POSITIVE_CLV_RATE}")
        market_state[market] = {"betting_certified": not f, "failures": f}
        failures.extend(f"{market}:{x}" for x in f)
    return {"certified": not failures, "markets": market_state, "failures": failures}
