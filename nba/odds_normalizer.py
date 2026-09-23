from __future__ import annotations

from typing import Any
from .teams import canonical_team


def _selection_name(name: str, home: str, away: str, market: str) -> str | None:
    if market in {"h2h", "spreads"}:
        if canonical_team(name) == home:
            return "HOME"
        if canonical_team(name) == away:
            return "AWAY"
    elif market == "totals":
        if name.lower() == "over":
            return "OVER"
        if name.lower() == "under":
            return "UNDER"
    return None


def normalize_game(raw: dict[str, Any]) -> dict[str, Any]:
    home = canonical_team(str(raw.get("home_team") or ""))
    away = canonical_team(str(raw.get("away_team") or ""))
    out: dict[str, Any] = {
        "event_id": str(raw.get("id") or ""),
        "commence_time": raw.get("commence_time"),
        "home": home, "away": away,
        "markets": {"ML": [], "SPREAD": [], "TOTAL": []},
    }
    market_map = {"h2h": "ML", "spreads": "SPREAD", "totals": "TOTAL"}
    for bookmaker in raw.get("bookmakers") or []:
        book_key = str(bookmaker.get("key") or bookmaker.get("title") or "").lower()
        for market in bookmaker.get("markets") or []:
            source = str(market.get("key") or "")
            canonical = market_map.get(source)
            if canonical is None:
                continue
            rows = []
            for outcome in market.get("outcomes") or []:
                selection = _selection_name(str(outcome.get("name") or ""), home, away, source)
                if selection is None:
                    continue
                row = {"selection": selection, "price": outcome.get("price")}
                if outcome.get("point") is not None:
                    row["point"] = outcome["point"]
                rows.append(row)
            if rows:
                out["markets"][canonical].append({
                    "bookmaker": book_key,
                    "last_update": market.get("last_update") or bookmaker.get("last_update"),
                    "selections": rows,
                })
    return out
