from __future__ import annotations

import math
from typing import Any


def _price(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) and out > 1.0 else None


def no_vig_pair(price_a: float, price_b: float) -> tuple[float, float]:
    qa, qb = 1.0/float(price_a), 1.0/float(price_b)
    s = qa + qb
    return qa/s, qb/s


def best_execution(books: list[dict[str, Any]], selection: str, *, point: float | None = None) -> dict[str, Any] | None:
    best = None
    for book in books:
        for row in book.get("selections") or []:
            if str(row.get("selection")) != selection:
                continue
            if point is not None and row.get("point") is not None and abs(float(row["point"]) - float(point)) > 1e-9:
                continue
            price = _price(row.get("price"))
            if price is None:
                continue
            candidate = {"bookmaker": book.get("bookmaker"), "price": price, "point": row.get("point")}
            if best is None or price > best["price"]:
                best = candidate
    return best


def pinnacle_no_vig(books: list[dict[str, Any]], left: str, right: str, *, point: float | None = None) -> dict[str, float] | None:
    for book in books:
        if str(book.get("bookmaker") or "").lower() != "pinnacle":
            continue
        found: dict[str, float] = {}
        for row in book.get("selections") or []:
            if row.get("selection") not in {left, right}:
                continue
            if point is not None and row.get("point") is not None and abs(float(row["point"]) - float(point)) > 1e-9:
                continue
            price = _price(row.get("price"))
            if price:
                found[str(row["selection"])] = price
        if left in found and right in found:
            lp, rp = no_vig_pair(found[left], found[right])
            return {left: lp, right: rp}
    return None
