"""Manual current NBA market-coverage diagnostic. One Odds API request."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from .acquisition import fetch_nba_odds_diagnostic
from .odds_normalizer import normalize_game
from .market import paired_price_rows
from .odds_budget import reserve as reserve_odds_request

def run(*, require_events: bool=False, budget_path: str='runtime/odds_budget.json')->dict:
    reserve_odds_request(path=budget_path,purpose='market_smoke')
    payload=fetch_nba_odds_diagnostic()
    events=[normalize_game(row) for row in payload["events"]]
    market_counts={"ML":0,"SPREAD":0,"TOTAL":0}
    paired_pinnacle_counts={"ML":0,"SPREAD":0,"TOTAL":0}
    pinnacle_events=0
    complete_pinnacle_events=0
    for event in events:
        event_pairs=set()
        has_pin=False
        for market in market_counts:
            books=event.get("markets",{}).get(market,[])
            market_counts[market]+=sum(bool(book.get("selections")) for book in books)
            for book in books:
                if str(book.get("bookmaker") or "").lower() != "pinnacle":
                    continue
                has_pin=has_pin or bool(book.get("selections"))
                left,right=("OVER","UNDER") if market=="TOTAL" else ("HOME","AWAY")
                points=(None,) if market=="ML" else tuple(
                    row.get("point") for row in book.get("selections") or []
                    if row.get("selection")==left and row.get("point") is not None
                )
                if any(paired_price_rows(book,left,right,point=point)
                       for point in points):
                    event_pairs.add(market)
            paired_pinnacle_counts[market]+=int(market in event_pairs)
        pinnacle_events+=int(has_pin)
        complete_pinnacle_events+=int(len(event_pairs)==3)
    result={
        "schema":"pulsar-nba-market-smoke-v2","checked_at":datetime.now(timezone.utc).isoformat(),"request_count":1,
        "events":len(events),"pinnacle_events":pinnacle_events,
        "market_book_counts":market_counts,
        "paired_pinnacle_market_events":paired_pinnacle_counts,
        "complete_pinnacle_events":complete_pinnacle_events,
        "quota":payload.get("usage") or {},
        "coverage_ready":complete_pinnacle_events>0,
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
