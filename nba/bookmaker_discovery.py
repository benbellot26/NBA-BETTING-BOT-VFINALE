"""One-request diagnostic of currently available NBA bookmakers."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
from typing import Any
from .acquisition import fetch_nba_odds_diagnostic
from .odds_budget import reserve as reserve_odds_request
from .odds_normalizer import normalize_game
from .market import consensus_no_vig, representative_point

REQUIRED={"h2h","spreads","totals"}

def run(*,budget_path:str="runtime/odds_budget.json")->dict[str,Any]:
    reserve_odds_request(path=budget_path,purpose="bookmaker_discovery")
    payload=fetch_nba_odds_diagnostic(bookmakers=None,regions="eu,us")
    event_counts=Counter();complete=Counter()
    market_counts={name:Counter() for name in REQUIRED}
    checked_at=datetime.now(timezone.utc).isoformat()
    consensus_market_events={"ML":0,"SPREAD":0,"TOTAL":0}
    complete_consensus_events=0
    for raw_event in payload["events"]:
        for book in raw_event.get("bookmakers") or []:
            key=str(book.get("key") or book.get("title") or "").strip().lower()
            if not key:continue
            markets={str(m.get("key") or "") for m in book.get("markets") or [] if m.get("outcomes")}
            event_counts[key]+=1
            for market in REQUIRED:
                if market in markets:market_counts[market][key]+=1
            if REQUIRED.issubset(markets):complete[key]+=1
        event=normalize_game(raw_event)
        found=set()
        specs=(
            ("ML","HOME","AWAY",None),
            ("SPREAD","HOME","AWAY",representative_point(
                event["markets"]["SPREAD"],"HOME","AWAY")),
            ("TOTAL","OVER","UNDER",representative_point(
                event["markets"]["TOTAL"],"OVER","UNDER")),
        )
        for market,left,right,point in specs:
            if market!="ML" and point is None:
                continue
            benchmark=consensus_no_vig(
                event["markets"][market],left,right,point=point,
                analyzed_at=checked_at,min_books=3,
            )
            if benchmark is not None:
                consensus_market_events[market]+=1
                found.add(market)
        complete_consensus_events+=int(len(found)==3)
    pinnacle_present="pinnacle" in event_counts
    if not payload["events"]:
        pinnacle_state="NO_NBA_EVENTS"
    elif pinnacle_present:
        pinnacle_state="PRESENT_IN_DISCOVERY"
    else:
        pinnacle_state="ABSENT_FROM_CURRENT_SNAPSHOT"
    return {"schema":"pulsar-nba-bookmaker-discovery-v1",
            "checked_at":checked_at,
            "role":"MARKET_DIAGNOSTIC_ONLY","request_count":1,
            "events":len(payload["events"]),
            "bookmaker_event_counts":dict(event_counts.most_common()),
            "complete_featured_market_events":dict(complete.most_common()),
            "market_event_counts":{k:dict(v.most_common()) for k,v in market_counts.items()},
            "pinnacle_present":pinnacle_present,
            "pinnacle_state":pinnacle_state,
            "consensus_market_events":consensus_market_events,
            "complete_consensus_events":complete_consensus_events,
            "consensus_role":"EVALUATION_ONLY",
            "consensus_replaces_pinnacle":False,
            "benchmark_changed":False,"betting_certified":False,
            "quota":payload.get("usage") or {}}

def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--output",default="runtime/bookmaker_discovery.json")
    a=p.parse_args();result=run();target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2),encoding="utf-8");print(json.dumps(result,indent=2))
if __name__=="__main__":main()
