"""Convert operational health into a GitHub Actions failure signal."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def evaluate(report: dict)->dict:
    state=str(report.get("state") or "")
    blocked=state in {"ANALYSIS_BLOCKED","PROVIDER_DEGRADED"}
    return {"ok":not blocked,"state":state,"failures":report.get("failures") or []}

def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--input",default="runtime/health.json");a=p.parse_args()
    result=evaluate(json.loads(Path(a.input).read_text(encoding="utf-8")))
    print(json.dumps(result,indent=2))
    if not result["ok"]: raise SystemExit(1)
if __name__=="__main__":main()
