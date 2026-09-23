"""Synthetic full-evening rehearsal from model analysis through close and settlement."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from .close_runtime import _close_row
from .e2e_dryrun import run as analysis_run
from .settlement import settle_candidate

def run(*, output_dir: str|Path="runtime/rehearsal")->dict:
    root=Path(output_dir);root.mkdir(parents=True,exist_ok=True)
    analysis=analysis_run()
    entry={
        "entry_key":"rehearsal|ML|home_ml","game_id":analysis["game_id"],
        "market":"ML","selection":"home_ml","line":None,"price":2.0,
        "stake_fraction":.01,
    }
    event={"markets":{"ML":[{"bookmaker":"pinnacle","selections":[
        {"selection":"HOME","price":1.90},{"selection":"AWAY","price":2.00}
    ]}]}}
    close=_close_row(entry,event,"2026-11-15T22:19:00Z","synthetic-rehearsal")
    settled=settle_candidate(entry,home_score=118,away_score=112)
    report={
        "schema":"pulsar-nba-full-rehearsal-v1","role":"SYNTHETIC_REHEARSAL_ONLY",
        "analysis":analysis,"close_contract":close,"settlement":settled,
        "prospective_evidence_eligible":False,"betting_certified":False,
        "real_betting_authorized":False,"odds_api_requests":0,
        "stages":["provider_fixture","analysis","market_pair","close_capture","settlement","persistence"],
    }
    for name,payload in (("analysis.json",analysis),("close.json",close),("settlement.json",settled),("report.json",report)):
        (root/name).write_text(json.dumps(payload,indent=2,sort_keys=True),encoding="utf-8")
    return report

def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--output-dir",default="runtime/rehearsal");a=p.parse_args();print(json.dumps(run(output_dir=a.output_dir),indent=2))
if __name__=="__main__":main()
