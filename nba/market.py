from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any


def _price(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 1.0 else None


def no_vig_pair(price_a: float, price_b: float) -> tuple[float, float]:
    a, b = _price(price_a), _price(price_b)
    if a is None or b is None:
        raise ValueError("valid positive decimal odds are required")
    qa, qb = 1.0 / a, 1.0 / b
    return qa / (qa + qb), qb / (qa + qb)


def _point_equal(value: Any, expected: float | None) -> bool:
    if expected is None:
        return value is None
    try:
        return value is not None and math.isfinite(float(value)) and abs(float(value) - expected) <= 1e-7
    except (TypeError, ValueError):
        return False


def paired_price_rows(
    book: dict[str, Any], left: str, right: str, *, point: float | None = None
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Select *exactly* the same settlement contract on both sides.

    For home/away spread, the counterpart is the NEGATIVE handicap.
    For Over/Under, both point values are the same. ML has no point.
    """
    selections = book.get("selections") or []
    opponent_point = -point if point is not None and {left, right} == {"HOME", "AWAY"} else point
    left_row = next((r for r in selections
                     if r.get("selection") == left and _point_equal(r.get("point"), point)
                     and _price(r.get("price")) is not None), None)
    right_row = next((r for r in selections
                      if r.get("selection") == right and _point_equal(r.get("point"), opponent_point)
                      and _price(r.get("price")) is not None), None)
    return (left_row, right_row) if left_row is not None and right_row is not None else None


def best_execution(
    books: list[dict[str, Any]], selection: str, *, point: float | None = None
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for book in books:
        for row in book.get("selections") or []:
            if row.get("selection") != selection or not _point_equal(row.get("point"), point):
                continue
            price = _price(row.get("price"))
            if price is None:
                continue
            candidate = {
                "bookmaker": book.get("bookmaker"),
                "price": price,
                "point": row.get("point"),
                "last_update": book.get("last_update"),
            }
            if best is None or price > best["price"]:
                best = candidate
    return best


def pinnacle_no_vig(
    books: list[dict[str, Any]], left: str, right: str, *, point: float | None = None
) -> dict[str, float] | None:
    for book in books:
        if str(book.get("bookmaker") or "").lower() != "pinnacle":
            continue
        pair = paired_price_rows(book, left, right, point=point)
        if pair is not None:
            lp, rp = no_vig_pair(pair[0]["price"], pair[1]["price"])
            return {left: lp, right: rp}
    return None


def fresh_quote(last_update: str | None, analyzed_at: str, *, max_age_minutes: float = 15.0) -> bool:
    if not last_update:
        return False
    try:
        quote = datetime.fromisoformat(last_update.replace("Z", "+00:00"))
        analyzed = datetime.fromisoformat(analyzed_at.replace("Z", "+00:00"))
        if quote.tzinfo is None or analyzed.tzinfo is None:
            return False
        age = (analyzed.astimezone(timezone.utc) - quote.astimezone(timezone.utc)).total_seconds() / 60.0
        return -2.0 <= age <= max_age_minutes
    except (ValueError, TypeError):
        return False
