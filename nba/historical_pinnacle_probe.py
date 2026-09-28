"""One-request historical Pinnacle availability probe.

This diagnostic answers whether The Odds API historical NBA endpoint exposes
Pinnacle for a known past game. It is diagnostic only and never model evidence
or certification authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .acquisition import fetch_historical_nba_odds_diagnostic
from .provider_http import ProviderDiagnosticError
from .market import paired_price_rows
from .odds_budget import reserve as reserve_odds_request
from .odds_normalizer import normalize_game
from .schedule import season_for_date
from .teams import canonical_team

SCHEMA="pulsar-nba-historical-pinnacle-probe-v1"


def _dt(value: str) -> datetime:
    parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("probe timestamp requires timezone")
    return parsed.astimezone(timezone.utc)


def run(
    *,
    game_date:str="2026-03-20",
    away:str="Golden State Warriors",
    home:str="Detroit Pistons",
    requested_at:str="2026-03-20T20:00:00+00:00",
    output:str="runtime/historical_pinnacle_probe.json",
    budget_path:str="runtime/odds_budget.json",
)->dict[str,Any]:
    season=season_for_date(game_date)
    requested=_dt(requested_at)
    if requested.date().isoformat()!=game_date:
        raise ValueError("requested_at must be on game_date")

    reserve_odds_request(path=budget_path,purpose="historical_pinnacle_probe")
    try:
        payload=fetch_historical_nba_odds_diagnostic(
            date_iso=requested.isoformat(),bookmakers="pinnacle")
    except ProviderDiagnosticError as exc:
        result={
            "schema":SCHEMA,
            "role":"MARKET_DIAGNOSTIC_ONLY",
            "season":season,
            "game_date":game_date,
            "away":away,
            "home":home,
            "requested_at":requested.isoformat(),
            "state":"HISTORICAL_PROVIDER_ERROR",
            "historical_pinnacle_available":False,
            "provider_http_status":exc.status,
            "provider_error_code":exc.provider_code,
            "request_count":1,
            "used_for_certification":False,
            "pinnacle_replacement":False,
            "betting_certified":False,
        }
        target=Path(output);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
        return result
    events=[normalize_game(row) for row in payload["data"]]
    matches=[
        event for event in events
        if canonical_team(event["away"])==canonical_team(away)
        and canonical_team(event["home"])==canonical_team(home)
        and _dt(event["commence_time"])>requested
    ]
    if len(matches)>1:
        raise ValueError("ambiguous historical odds event")
    event=matches[0] if matches else None

    pair_state={"ML":False,"SPREAD":False,"TOTAL":False}
    market_books={"ML":0,"SPREAD":0,"TOTAL":0}
    pinnacle_books={"ML":0,"SPREAD":0,"TOTAL":0}
    if event is not None:
        for market,left,right in (
            ("ML","HOME","AWAY"),
            ("SPREAD","HOME","AWAY"),
            ("TOTAL","OVER","UNDER"),
        ):
            books=event["markets"].get(market) or []
            market_books[market]=len(books)
            pins=[
                book for book in books
                if str(book.get("bookmaker") or "").lower()=="pinnacle"
            ]
            pinnacle_books[market]=len(pins)
            for book in pins:
                points=(None,) if market=="ML" else tuple(
                    row.get("point") for row in book.get("selections") or []
                    if row.get("selection")==left and row.get("point") is not None
                )
                if any(paired_price_rows(book,left,right,point=point) for point in points):
                    pair_state[market]=True
                    break

    snapshot_at=str(payload.get("timestamp") or "")
    snapshot_age_minutes=None
    if snapshot_at:
        snapshot_age_minutes=(requested-_dt(snapshot_at)).total_seconds()/60.0

    if event is None:
        state="EVENT_NOT_FOUND"
    elif all(pair_state.values()):
        state="PINNACLE_HISTORICAL_READY"
    elif any(pinnacle_books.values()):
        state="PINNACLE_HISTORICAL_PARTIAL"
    else:
        state="PINNACLE_HISTORICAL_ABSENT"

    result={
        "schema":SCHEMA,
        "role":"MARKET_DIAGNOSTIC_ONLY",
        "season":season,
        "game_date":game_date,
        "away":away,
        "home":home,
        "requested_at":requested.isoformat(),
        "matched_tipoff_at":event.get("commence_time") if event is not None else None,
        "provider_snapshot_at":snapshot_at or None,
        "snapshot_age_minutes":snapshot_age_minutes,
        "events":len(events),
        "matched_event":event is not None,
        "market_books":market_books,
        "pinnacle_books":pinnacle_books,
        "paired_pinnacle_markets":pair_state,
        "state":state,
        "historical_pinnacle_available":state in {
            "PINNACLE_HISTORICAL_READY","PINNACLE_HISTORICAL_PARTIAL"
        },
        "request_count":1,
        "quota":payload.get("usage") or {},
        "used_for_certification":False,
        "pinnacle_replacement":False,
        "betting_certified":False,
    }
    target=Path(output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    return result


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--date",default="2026-03-20")
    p.add_argument("--away",default="Golden State Warriors")
    p.add_argument("--home",default="Detroit Pistons")
    p.add_argument("--requested-at",default="2026-03-20T20:00:00+00:00")
    p.add_argument("--output",default="runtime/historical_pinnacle_probe.json")
    p.add_argument("--budget",default="runtime/odds_budget.json")
    a=p.parse_args()
    print(json.dumps(run(
        game_date=a.date,away=a.away,home=a.home,
        requested_at=a.requested_at,output=a.output,
        budget_path=a.budget),indent=2))


if __name__=="__main__":
    main()
