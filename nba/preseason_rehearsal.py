"""Preseason rehearsal. Never writes prospective evidence and never authorizes a bet."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .e2e_dryrun import run as fixture_run
from .providers import OfficialNBAProvider

def run(*, target_date: str | None = None, official_source: bool = False,
        snapshot_root: str = "runtime/rehearsal_snapshots") -> dict[str, Any]:
    fixture=fixture_run()
    result={
        "schema":"pulsar-nba-preseason-rehearsal-v1","role":"PRESEASON_REHEARSAL_ONLY",
        "generated_at":datetime.now(timezone.utc).isoformat(),"betting_certified":False,
        "prospective_evidence_eligible":False,"paper_eligible":False,
        "odds_api_requests":0,"fixture":fixture,"official_source":None,"errors":[]
    }
    if official_source:
        if not target_date: raise ValueError("target_date is required for official source rehearsal")
        try:
            source=OfficialNBAProvider(snapshot_root=snapshot_root).capture(target_date=target_date)
            result["official_source"]={
                "ok":True,"provider_id":source.provider_id,"role":source.role,
                "target_date":source.target_date,"schedule_games":len(source.schedule),
                "stats_observed_at":source.stats.get("observed_at"),
                "injury_reported_at":source.injuries.get("reported_at"),
            }
        except Exception as exc:
            result["official_source"]={"ok":False,"error_type":type(exc).__name__}
            result["errors"].append(f"official_source:{type(exc).__name__}")
    return result

def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--date");p.add_argument("--official-source",action="store_true");p.add_argument("--output",default="runtime/preseason_rehearsal.json")
    a=p.parse_args();result=run(target_date=a.date,official_source=a.official_source);target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result,indent=2),encoding="utf-8");print(json.dumps(result,indent=2))
if __name__=="__main__":main()
