"""Generate a compact operational-health report from persisted runtime evidence."""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

def _json(path: Path) -> dict[str, Any] | None:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError): return None

def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError, TypeError): return []

def build(root: str | Path = "runtime") -> dict[str, Any]:
    root=Path(root); ev=root/"evidence"
    live=_json(root/"live_run.json") or {}
    provider=_json(root/"provider_smoke.json") or {}
    performance=_json(ev/"performance.json") or {}
    audit=_json(ev/"audit.json") or {}
    forecasts=_jsonl(ev/"final_forecasts.jsonl")
    paper=_jsonl(ev/"paper_entries.jsonl")
    closes=_jsonl(ev/"close_ledger.jsonl")
    settled=_jsonl(ev/"settled_paper.jsonl")
    failures=list(live.get("failures") or [])
    state="READY_FOR_REHEARSAL"
    if provider and provider.get("ok") is False: state="PROVIDER_DEGRADED"
    if live.get("status")=="NO_ANALYSIS": state="ANALYSIS_BLOCKED"
    return {
        "schema":"pulsar-nba-health-v1",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "state":state,
        "live_operational":False,
        "real_betting_authorized":False,
        "last_live_status":live.get("status"),
        "last_target_date":live.get("target_date"),
        "last_odds_api_requests":int(live.get("odds_api_requests") or 0),
        "provider_ok":provider.get("ok"),
        "provider_details":provider.get("providers") or {},
        "evidence":{
            "forecasts":len(forecasts),"paper_entries":len(paper),
            "closes":len(closes),"settled":len(settled),
            "audit_ok":audit.get("ok"),"completed_games":performance.get("games",0),
        },
        "failures":failures,
    }

def main()->None:
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--root",default="runtime");p.add_argument("--output",default="runtime/health.json")
    a=p.parse_args();result=build(a.root);target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result,indent=2),encoding="utf-8");print(json.dumps(result,indent=2))
if __name__=="__main__":main()
