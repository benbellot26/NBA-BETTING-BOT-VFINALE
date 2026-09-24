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

REQUIRED={"h2h","spreads","totals"}

def run(*,budget_path:str="runtime/odds_budget.json")->dict[str,Any]:
    reserve_odds_request(path=budget_path,purpose="bookmaker_discovery")
    payload=fetch_nba_odds_diagnostic(bookmakers=None,regions="eu,us")
    event_counts=Counter();complete=Counter()
    market_counts={name:Counter() for name in REQUIRED}
    for event in payload["events"]:
        for book in event.get("bookmakers") or []:
            key=str(book.get("key") or book.get("title") or "").strip().lower()
            if not key:continue
            markets={str(m.get("key") or "") for m in book.get("markets") or [] if m.get("outcomes")}
            event_counts[key]+=1
            for market in REQUIRED:
                if market in markets:market_counts[market][key]+=1
            if REQUIRED.issubset(markets):complete[key]+=1
    return {"schema":"pulsar-nba-bookmaker-discovery-v1",
            "checked_at":datetime.now(timezone.utc).isoformat(),
            "role":"MARKET_DIAGNOSTIC_ONLY","request_count":1,
            "events":len(payload["events"]),
            "bookmaker_event_counts":dict(event_counts.most_common()),
            "complete_featured_market_events":dict(complete.most_common()),
            "market_event_counts":{k:dict(v.most_common()) for k,v in market_counts.items()},
            "pinnacle_present":"pinnacle" in event_counts,
            "benchmark_changed":False,"betting_certified":False,
            "quota":payload.get("usage") or {}}

def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--output",default="runtime/bookmaker_discovery.json")
    a=p.parse_args();result=run();target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2),encoding="utf-8");print(json.dumps(result,indent=2))
if __name__=="__main__":main()
