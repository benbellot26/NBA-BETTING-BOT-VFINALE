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

def _age_hours(value: Any, now: datetime) -> float | None:
    try:
        parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if parsed.tzinfo is None: return None
        return (now-parsed.astimezone(timezone.utc)).total_seconds()/3600.0
    except (TypeError,ValueError):
        return None

def build(root: str | Path = "runtime", *, at: str | None = None) -> dict[str, Any]:
    root=Path(root); ev=root/"evidence"
    now=(datetime.fromisoformat(at.replace("Z","+00:00")) if at else datetime.now(timezone.utc))
    if now.tzinfo is None: raise ValueError("health report time needs timezone")
    now=now.astimezone(timezone.utc)
    live=_json(root/"live_run.json") or {}
    provider=_json(root/"provider_smoke.json") or {}
    performance=_json(ev/"performance.json") or {}
    market=_json(root/"market_smoke.json") or {}
    budget=_json(root/"odds_budget.json") or {}
    readiness=_json(root/"readiness_gate.json") or {}
    runner_probe=_json(root/"runner_probe.json") or {}
    audit=_json(ev/"audit.json") or {}
    forecasts=_jsonl(ev/"final_forecasts.jsonl")
    paper=_jsonl(ev/"paper_entries.jsonl")
    closes=_jsonl(ev/"close_ledger.jsonl")
    settled=_jsonl(ev/"settled_paper.jsonl")
    failures=list(live.get("failures") or [])
    provider_age=_age_hours(provider.get("checked_at"),now) if provider else None
    market_age=_age_hours(market.get("checked_at"),now) if market else None
    provider_fresh=provider_age is not None and -0.1 <= provider_age <= 192
    market_fresh=market_age is not None and -0.1 <= market_age <= 72
    provider_state=str(provider.get("state") or "") if provider else ""
    state="READY_FOR_REHEARSAL"
    if provider and not provider_fresh:
        state="DIAGNOSTIC_STALE"
    elif provider_fresh and provider_state=="BLOCKED":
        state="PROVIDER_DEGRADED"
    elif provider_fresh and provider_state=="WAITING_FOR_PUBLICATION":
        state="WAITING_FOR_PUBLICATION"
    if market and not market_fresh and state=="READY_FOR_REHEARSAL":
        state="DIAGNOSTIC_STALE"
    if live.get("status")=="NO_ANALYSIS": state="ANALYSIS_BLOCKED"
    return {
        "schema":"pulsar-nba-health-v1",
        "generated_at":now.isoformat(),
        "state":state,
        "live_operational":False,
        "real_betting_authorized":False,
        "last_live_status":live.get("status"),
        "last_target_date":live.get("target_date"),
        "last_odds_api_requests":int(live.get("odds_api_requests") or 0),
        "odds_budget_unit":"REQUESTS_NOT_PROVIDER_CREDITS",
        "provider_ok":provider.get("operational_ready",provider.get("ok")),
        "provider_state":provider_state or None,
        "diagnostics":{"provider_age_hours":provider_age,"provider_fresh":provider_fresh,"market_age_hours":market_age,"market_fresh":market_fresh},
        "provider_details":provider.get("providers") or {},
        "market_coverage_ready":market.get("coverage_ready"),
        "ready_for_real_rehearsal":readiness.get("ready_for_real_rehearsal"),
        "readiness_failures":readiness.get("failures") or [],
        "runner_probe":{"checked_at":runner_probe.get("checked_at"),"reachable_routes":runner_probe.get("reachable_routes") or [],"probes":runner_probe.get("probes") or {}},
        "odds_budget":{"used":int(budget.get("used") or 0),"limit":budget.get("limit"),"remaining":budget.get("remaining"),"purposes":budget.get("purposes") or {}},
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
