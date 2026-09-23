from __future__ import annotations

from typing import Any

MAX_CORRELATED_GAME_EXPOSURE=.0125


def dependency_key(row: dict[str,Any]) -> tuple[str,str]:
    game=str(row.get("game_id") or "UNKNOWN")
    selection=str(row.get("selection") or "")
    if selection.startswith("home_") or selection=="over": direction="HOME_OR_OVER"
    elif selection.startswith("away_") or selection=="under": direction="AWAY_OR_UNDER"
    else: direction="OTHER"
    return game,direction


def apply_correlation_cap(rows: list[dict[str,Any]]) -> list[dict[str,Any]]:
    used={}; out=[]
    for row in rows:
        r=dict(row); key=dependency_key(r); desired=max(0.0,float(r.get("stake_fraction") or 0.0)); allowed=max(0.0,MAX_CORRELATED_GAME_EXPOSURE-used.get(key,0.0)); stake=min(desired,allowed); r["stake_fraction"]=stake; used[key]=used.get(key,0.0)+stake; out.append(r)
    return out
