from __future__ import annotations

from typing import Any


def settle_candidate(candidate: dict[str,Any], *, home_score: int, away_score: int) -> dict[str,Any]:
    row=dict(candidate); selection=str(row.get("selection") or ""); line=row.get("line")
    margin=float(home_score-away_score); total=float(home_score+away_score)
    value=None
    if selection=="home_ml": value=margin
    elif selection=="away_ml": value=-margin
    elif selection=="home_spread": value=margin+float(line or 0)
    elif selection=="away_spread": value=-margin+float(line or 0)
    elif selection=="over": value=total-float(line)
    elif selection=="under": value=float(line)-total
    else: raise ValueError(f"unsupported selection: {selection}")
    result="WIN" if value>0 else "LOSS" if value<0 else "PUSH"
    price=float(row.get("price") or 0)
    stake=float(row.get("stake_fraction") or 0)
    profit=stake*(price-1) if result=="WIN" else -stake if result=="LOSS" else 0.0
    row.update({"home_score":home_score,"away_score":away_score,"settlement":result,"profit_bankroll_fraction":profit})
    return row


def aggregate(rows: list[dict[str,Any]]) -> dict[str,Any]:
    settled=[r for r in rows if r.get("settlement") in {"WIN","LOSS","PUSH"}]
    wins=sum(r["settlement"]=="WIN" for r in settled); losses=sum(r["settlement"]=="LOSS" for r in settled); pushes=len(settled)-wins-losses
    stake=sum(float(r.get("stake_fraction") or 0) for r in settled); profit=sum(float(r.get("profit_bankroll_fraction") or 0) for r in settled)
    return {"n":len(settled),"wins":wins,"losses":losses,"pushes":pushes,"stake_fraction":stake,"profit_fraction":profit,"roi":profit/stake if stake else None}
