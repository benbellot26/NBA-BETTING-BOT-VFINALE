from __future__ import annotations

from typing import Any


def _selection_name(name: str, home: str, away: str, market: str) -> str | None:
    if market == "h2h":
        if name == home: return "HOME"
        if name == away: return "AWAY"
    if market == "spreads":
        if name == home: return "HOME"
        if name == away: return "AWAY"
    if market == "totals":
        low=name.lower()
        if low == "over": return "OVER"
        if low == "under": return "UNDER"
    return None


def normalize_game(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize one The Odds API NBA event into Pulsar's market contract."""
    home=str(raw.get("home_team") or ""); away=str(raw.get("away_team") or "")
    out={"event_id":str(raw.get("id") or ""),"commence_time":raw.get("commence_time"),"home":home,"away":away,"markets":{"ML":[],"SPREAD":[],"TOTAL":[]}}
    market_map={"h2h":"ML","spreads":"SPREAD","totals":"TOTAL"}
    for bookmaker in raw.get("bookmakers") or []:
        book_key=str(bookmaker.get("key") or bookmaker.get("title") or "")
        for market in bookmaker.get("markets") or []:
            source_key=str(market.get("key") or "")
            canonical=market_map.get(source_key)
            if not canonical: continue
            rows=[]
            for outcome in market.get("outcomes") or []:
                selection=_selection_name(str(outcome.get("name") or ""),home,away,source_key)
                if not selection: continue
                row={"selection":selection,"price":outcome.get("price")}
                if outcome.get("point") is not None: row["point"]=outcome.get("point")
                rows.append(row)
            if rows:
                out["markets"][canonical].append({"bookmaker":book_key,"last_update":market.get("last_update") or bookmaker.get("last_update"),"selections":rows})
    return out
