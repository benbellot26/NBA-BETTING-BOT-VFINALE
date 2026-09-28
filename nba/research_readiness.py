"""Unified research-readiness matrix over persisted NBA evidence.

This report is descriptive and operational. It cannot authorize betting,
provider promotion, model promotion or substitute consensus for Pinnacle.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def _json(path: Path) -> dict[str, Any]:
    try:
        value=json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError,TypeError):
        return {}


def _jsonl(path: Path) -> list[dict[str,Any]]:
    try:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError,ValueError,TypeError):
        return []


def _item(
    *,
    state:str,
    ready:bool,
    blocker:str|None=None,
    next_action:str|None=None,
    **details:Any,
)->dict[str,Any]:
    row={"state":state,"ready":bool(ready)}
    if blocker: row["blocker"]=blocker
    if next_action: row["next_action"]=next_action
    row.update(details)
    return row


def build(root:str|Path="runtime")->dict[str,Any]:
    root=Path(root)
    ev=root/"evidence"
    provider=_json(root/"provider_smoke.json")
    market=_json(root/"market_smoke.json")
    discovery=_json(root/"bookmaker_discovery.json")
    historical_probe=_json(root/"historical_pinnacle_probe.json")
    gamebook=_json(root/"gamebook_reference"/"stat_pack.json")
    provider_shadow=_json(root/"provider_shadow"/"status.json")
    provider_shadow_gate=_json(root/"provider_shadow"/"review_gate.json")
    v2_gate=_json(root/"research"/"v2_learned_gate.json")
    v2_prospective=_json(root/"research"/"v2_prospective_performance.json")
    forecasts=_jsonl(ev/"final_forecasts.jsonl")
    outcomes=_jsonl(ev/"final_outcomes.jsonl")
    v2_live=_jsonl(root/"research"/"v2_live_forecasts.jsonl")

    providers=provider.get("providers") or {}
    stats=providers.get("stats") or {}
    injuries=providers.get("injuries") or {}
    schedule=providers.get("schedule") or {}

    canonical_ready=provider.get("operational_ready") is True
    if canonical_ready:
        canonical=_item(
            state="READY",ready=True,
            next_action="collect immutable prospective V1 evidence",
        )
    else:
        canonical=_item(
            state=str(provider.get("state") or "UNKNOWN"),
            ready=False,
            blocker="canonical_provider_not_operational",
            next_action="wait for/currently repair official stats + injury availability",
            schedule_state=schedule.get("state"),
            stats_state=stats.get("state"),
            injury_state=injuries.get("state"),
        )

    current_pin_ready=market.get("coverage_ready") is True
    current_pinnacle=_item(
        state=str(market.get("availability_state") or "UNKNOWN"),
        ready=current_pin_ready,
        blocker=None if current_pin_ready else "current_pinnacle_unavailable",
        next_action=(
            "capture prospective Pinnacle entry/close evidence"
            if current_pin_ready else
            "keep benchmark unchanged and monitor current availability"
        ),
        targeted_events=int(market.get("events") or 0),
        pinnacle_events=int(market.get("pinnacle_events") or 0),
        regional_pinnacle_present=discovery.get("pinnacle_present"),
        complete_consensus_events=int(discovery.get("complete_consensus_events") or 0),
        replacement_allowed=False,
    )

    historical_code=str(historical_probe.get("provider_error_code") or "")
    historical_ready=historical_probe.get("historical_pinnacle_available") is True
    if historical_code=="HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN":
        historical=_item(
            state="PLAN_BLOCKED",ready=False,
            blocker=historical_code,
            next_action="upgrade The Odds API plan only if historical research is desired",
            requests_should_be_skipped=True,
        )
    else:
        historical=_item(
            state=str(historical_probe.get("state") or "UNPROBED"),
            ready=historical_ready,
            blocker=None if historical_ready else historical_code or "historical_pinnacle_unavailable",
            next_action=(
                "recover research-only historical Pinnacle snapshots"
                if historical_ready else
                "rerun diagnostic after access/provider changes"
            ),
            requests_should_be_skipped=False,
        )

    gamebook_games=int(gamebook.get("gamebooks") or 0)
    gamebook_teams=int(gamebook.get("teams_with_games") or 0)
    shadow_ready=provider_shadow_gate.get("review_ready") is True
    if shadow_ready:
        shadow=_item(
            state="MANUAL_REVIEW_READY",ready=True,
            next_action="human provider review; no automatic promotion",
        )
    elif gamebook_games==0:
        shadow=_item(
            state="WAITING_FOR_SEASON_DATA",ready=False,
            blocker="no_completed_gamebook_history",
            next_action="collect official scorer gamebooks after NBA games begin",
            gamebooks=gamebook_games,teams_with_games=gamebook_teams,
        )
    else:
        shadow=_item(
            state=str(provider_shadow.get("status") or "COLLECTING"),
            ready=False,
            blocker="prospective_provider_shadow_evidence_incomplete",
            next_action="continue prospective gamebook-provider shadow collection",
            gamebooks=gamebook_games,
            teams_with_games=gamebook_teams,
            review_failures=provider_shadow_gate.get("failures") or [],
        )

    v2_review=v2_gate.get("review_ready") is True
    enriched_forecasts=sum(row.get("v2_features") is not None for row in forecasts)
    v2_resolved=int((v2_prospective.get("holdout_shadow") or {}).get("n") or 0)
    if v2_review:
        v2=_item(
            state="MANUAL_REVIEW_READY",ready=True,
            next_action="human model review; no automatic promotion",
            enriched_forecasts=enriched_forecasts,
            prospective_shadow_forecasts=len(v2_live),
            prospective_resolved=v2_resolved,
        )
    elif enriched_forecasts<400:
        v2=_item(
            state="COLLECTING_TRAINING_DATA",ready=False,
            blocker="enriched_pit_training_sample_below_400",
            next_action="collect enriched FINAL forecasts prospectively",
            enriched_forecasts=enriched_forecasts,
            minimum_train=400,
            prospective_shadow_forecasts=len(v2_live),
            prospective_resolved=v2_resolved,
        )
    else:
        v2=_item(
            state="SHADOW_VALIDATION",ready=False,
            blocker="manual_review_gate_not_passed",
            next_action="continue V2 walk-forward and prospective shadow validation",
            enriched_forecasts=enriched_forecasts,
            prospective_shadow_forecasts=len(v2_live),
            prospective_resolved=v2_resolved,
            gate_failures=v2_gate.get("failures") or [],
        )

    blockers=[
        name for name,row in (
            ("canonical_provider",canonical),
            ("current_pinnacle",current_pinnacle),
            ("gamebook_provider_shadow",shadow),
            ("learned_v2",v2),
        ) if not row["ready"]
    ]
    return {
        "schema":"pulsar-nba-research-readiness-v1",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "role":"RESEARCH_STATUS_ONLY",
        "live_betting_authorized":False,
        "betting_certified":False,
        "benchmark_bookmaker":"pinnacle",
        "pinnacle_replacement_allowed":False,
        "prospective_forecasts":len(forecasts),
        "resolved_outcomes":len(outcomes),
        "areas":{
            "canonical_provider":canonical,
            "current_pinnacle":current_pinnacle,
            "historical_pinnacle_research":historical,
            "gamebook_provider_shadow":shadow,
            "learned_v2":v2,
        },
        "primary_blockers":blockers,
    }


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--root",default="runtime")
    p.add_argument("--output",default="runtime/research_readiness.json")
    a=p.parse_args()
    result=build(a.root)
    target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
