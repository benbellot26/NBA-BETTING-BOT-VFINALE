from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
from .certification import certify
from .performance import brier,calibration_ece,logloss
from .schedule import fetch_schedule
from .settlement import settle_candidate
from .tracking import append_jsonl

def _read(path:str|Path)->list[dict[str,Any]]:
    p=Path(path)
    if not p.exists():return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
def _write(path:str|Path,payload:Any)->None:
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(payload,indent=2,sort_keys=True),encoding="utf-8")

def refresh(*,paper_path:str,close_path:str,settled_path:str,performance_path:str,certification_path:str)->dict[str,Any]:
    paper=_read(paper_path);closes={r["entry_key"]:r for r in _read(close_path)};settled_existing={r["entry_key"]:r for r in _read(settled_path)}
    finals={g.game_id:g for g in fetch_schedule() if g.final and g.home_score is not None and g.away_score is not None}
    for entry in paper:
        key=entry["entry_key"]
        if key in settled_existing or entry["game_id"] not in finals:continue
        g=finals[entry["game_id"]];row=settle_candidate(entry,home_score=g.home_score,away_score=g.away_score);row["entry_key"]=key
        close=closes.get(key)
        if close:row.update({"close_no_vig_probability":close.get("pinnacle_close_no_vig_probability"),"clv_pp":close.get("clv_pp"),"line_clv":close.get("line_clv"),"price_clv_comparable":close.get("price_clv_comparable")})
        append_jsonl(settled_path,row);settled_existing[key]=row
    rows=list(settled_existing.values());markets={}
    for market in ("ML","SPREAD","TOTAL"):
        m=[r for r in rows if r.get("market")==market and r.get("settlement") in {"WIN","LOSS"}];pairs=[(float(r["model_probability"]),1 if r["settlement"]=="WIN" else 0) for r in m];sharp=[r for r in m if r.get("price_clv_comparable") is True and r.get("close_no_vig_probability") is not None];clv=[float(r["clv_pp"]) for r in m if r.get("clv_pp") is not None]
        markets[market]={"n":len(m),"brier":sum(brier(p,y) for p,y in pairs)/len(pairs) if pairs else None,"logloss":sum(logloss(p,y) for p,y in pairs)/len(pairs) if pairs else None,"ece":calibration_ece(pairs) if pairs else 1.0,"paired_sharp_n":len(sharp),"model_brier_paired":sum(brier(float(r["model_probability"]),1 if r["settlement"]=="WIN" else 0) for r in sharp)/len(sharp) if sharp else None,"sharp_brier_paired":sum(brier(float(r["close_no_vig_probability"]),1 if r["settlement"]=="WIN" else 0) for r in sharp)/len(sharp) if sharp else None,"clv_n":len(clv),"mean_clv_pp":sum(clv)/len(clv) if clv else None,"positive_clv_rate":sum(x>0 for x in clv)/len(clv) if clv else 0.0}
    evidence={"schema":"pulsar-nba-performance-v1","games":len({r.get("game_id") for r in rows}),"settled_entries":len(rows),"markets":markets}
    state=certify(evidence);state["evidence"]=evidence;_write(performance_path,evidence);_write(certification_path,state);return state

def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--paper",default="runtime/evidence/paper_entries.jsonl");p.add_argument("--close",default="runtime/evidence/close_ledger.jsonl");p.add_argument("--settled",default="runtime/evidence/settled_paper.jsonl");p.add_argument("--performance",default="runtime/evidence/performance.json");p.add_argument("--certification",default="runtime/evidence/certification_candidate.json");a=p.parse_args();print(json.dumps(refresh(paper_path=a.paper,close_path=a.close,settled_path=a.settled,performance_path=a.performance,certification_path=a.certification),indent=2))
if __name__=="__main__":main()
