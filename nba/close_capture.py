from __future__ import annotations

from typing import Any

from .market import pinnacle_no_vig


def capture_close(*, market: str, selection: str, opposite: str, books: list[dict[str,Any]], point: float | None, captured_at: str) -> dict[str,Any]:
    sharp=pinnacle_no_vig(books,selection,opposite,point=point)
    if not sharp: raise ValueError("Pinnacle paired close unavailable")
    price=None
    for book in books:
        if str(book.get("bookmaker") or "").lower()!="pinnacle": continue
        for row in book.get("selections") or []:
            if row.get("selection")==selection and (point is None or row.get("point") is None or abs(float(row["point"])-float(point))<1e-9):
                price=float(row["price"]); break
    if price is None: raise ValueError("Pinnacle close price unavailable")
    return {"market":market,"selection":selection,"point":point,"pinnacle_price":price,"pinnacle_no_vig_probability":sharp[selection],"captured_at":captured_at}
