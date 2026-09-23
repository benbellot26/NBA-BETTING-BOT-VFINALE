"""Manual current NBA market-coverage diagnostic. One Odds API request."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from .acquisition import fetch_nba_odds_diagnostic
from .odds_normalizer import normalize_game

def run(*, require_events: bool=False)->dict:
    payload=fetch_nba_odds_diagnostic()
    events=[normalize_game(row) for row in payload["events"]]
    market_counts={"ML":0,"SPREAD":0,"TOTAL":0}
    pinnacle_events=0
    for event in events:
        has_pin=False
        for market in market_counts:
            books=event.get("markets",{}).get(market,[])
            market_counts[market]+=sum(bool(book.get("selections")) for book in books)
            has_pin=has_pin or any(str(book.get("bookmaker","")).lower()=="pinnacle" for book in books)
        pinnacle_events+=int(has_pin)
    result={
        "schema":"pulsar-nba-market-smoke-v1","request_count":1,
        "events":len(events),"pinnacle_events":pinnacle_events,
        "market_book_counts":market_counts,"quota":payload.get("usage") or {},
        "coverage_ready":bool(events) and pinnacle_events>0 and all(v>0 for v in market_counts.values()),
        "betting_certified":False,
    }
    if require_events and not result["coverage_ready"]:
        result["error"]="required NBA/Pinnacle featured-market coverage is absent"
    return result

def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--require-events",action="store_true");p.add_argument("--output")
    a=p.parse_args();result=run(require_events=a.require_events);payload=json.dumps(result,indent=2)
    if a.output:
        target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(payload,encoding="utf-8")
    print(payload)
    if a.require_events and not result["coverage_ready"]: raise SystemExit(1)
if __name__=="__main__":main()
