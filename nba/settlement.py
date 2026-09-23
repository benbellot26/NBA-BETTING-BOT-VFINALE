"""Deterministic research-paper settlement with strict contract validation."""
from __future__ import annotations

import math
from typing import Any


def _finite(value: Any, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a finite number") from None
    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be a finite number")
    return parsed


def _score(value: int, name: str) -> int:
    parsed = _finite(value, name)
    if parsed < 0 or not parsed.is_integer():
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(parsed)


def settle_candidate(
    candidate: dict[str, Any], *, home_score: int, away_score: int
) -> dict[str, Any]:
    home = _score(home_score, "home_score")
    away = _score(away_score, "away_score")
    row = dict(candidate)
    selection = str(row.get("selection") or "")
    market = str(row.get("market") or "")
    selections = {
        "home_ml": "ML", "away_ml": "ML",
        "home_spread": "SPREAD", "away_spread": "SPREAD",
        "over": "TOTAL", "under": "TOTAL",
    }
    if selection not in selections or market != selections[selection]:
        raise ValueError("unsupported or mismatched market/selection")
    line = None if market == "ML" else _finite(row.get("line"), "line")
    price = _finite(row.get("price"), "price")
    stake = _finite(row.get("stake_fraction", 0), "stake_fraction")
    if price <= 1:
        raise ValueError("decimal price must exceed 1")
    if not 0 <= stake <= 1:
        raise ValueError("stake fraction outside [0,1]")
    margin = home - away
    total = home + away
    if selection == "home_ml":
        delta = margin
    elif selection == "away_ml":
        delta = -margin
    elif selection == "home_spread":
        delta = margin + line
    elif selection == "away_spread":
        delta = -margin + line
    elif selection == "over":
        delta = total - line
    else:
        delta = line - total
    settlement = "WIN" if delta > 0 else "LOSS" if delta < 0 else "PUSH"
    profit = stake * (price - 1) if settlement == "WIN" else (
        -stake if settlement == "LOSS" else 0.0
    )
    row.update({
        "home_score": home, "away_score": away,
        "settlement": settlement,
        "profit_bankroll_fraction": profit,
    })
    return row


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    settled = [row for row in rows if row.get("settlement") in {"WIN", "LOSS", "PUSH"}]
    wins = sum(row["settlement"] == "WIN" for row in settled)
    losses = sum(row["settlement"] == "LOSS" for row in settled)
    pushes = len(settled) - wins - losses
    stake = sum(_finite(row.get("stake_fraction", 0), "stake_fraction") for row in settled)
    profit = sum(_finite(row.get("profit_bankroll_fraction", 0), "profit_bankroll_fraction")
                 for row in settled)
    return {
        "n": len(settled), "wins": wins, "losses": losses, "pushes": pushes,
        "stake_fraction": stake, "profit_fraction": profit,
        "roi": profit / stake if stake else None,
        "role": "PAPER_ONLY",
    }
