"""Score research-only historical Pinnacle entry recovery against outcomes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .model import ProbabilitySurface
from .performance import brier, calibration_ece, logloss


def _read(path: str | Path) -> list[dict[str, Any]]:
    target=Path(path)
    if not target.exists():
        return []
    return [
        json.loads(line)
        for line in target.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _proper(rows: list[tuple[float,int]]) -> dict[str,Any]:
    if not rows:
        return {"n":0,"brier":None,"logloss":None,"ece":None}
    return {
        "n":len(rows),
        "brier":sum(brier(p,y) for p,y in rows)/len(rows),
        "logloss":sum(logloss(p,y) for p,y in rows)/len(rows),
        "ece":calibration_ece(rows),
    }


def evaluate(
    *,
    forecasts_path: str="runtime/evidence/final_forecasts.jsonl",
    outcomes_path: str="runtime/evidence/final_outcomes.jsonl",
    recovery_path: str="runtime/research/pinnacle_historical_entry.jsonl",
    output_path: str="runtime/research/pinnacle_historical_performance.json",
) -> dict[str,Any]:
    forecasts={str(row.get("entry_key") or ""):row for row in _read(forecasts_path)}
    outcomes={str(row.get("game_id") or ""):row for row in _read(outcomes_path)}
    recovered=_read(recovery_path)

    sharp_pairs={m:[] for m in ("ML","SPREAD","TOTAL")}
    model_pairs={m:[] for m in ("ML","SPREAD","TOTAL")}
    ages={m:[] for m in ("ML","SPREAD","TOTAL")}
    resolved_keys=[]

    for row in recovered:
        if row.get("schema")!="pulsar-nba-historical-pinnacle-entry-v1":
            raise ValueError("unsupported historical Pinnacle recovery row")
        if row.get("role")!="HISTORICAL_EVALUATION_ONLY":
            raise ValueError("historical Pinnacle recovery role mismatch")
        if row.get("used_for_certification") is not False:
            raise ValueError("historical Pinnacle row claims certification use")
        if row.get("market_data_used_as_model_feature") is not False:
            raise ValueError("historical Pinnacle row claims model-feature use")
        forecast=forecasts.get(str(row.get("forecast_entry_key") or ""))
        outcome=outcomes.get(str(row.get("game_id") or ""))
        if forecast is None or outcome is None:
            continue
        probs=ProbabilitySurface(**forecast["probabilities"]).validated()
        home=float(outcome["home_score"]);away=float(outcome["away_score"])
        margin=home-away;total=home+away
        labels={
            "ML":int(margin>0) if margin!=0 else None,
            "SPREAD":int(margin+probs.spread_line>0) if margin+probs.spread_line!=0 else None,
            "TOTAL":int(total-probs.total_line>0) if total-probs.total_line!=0 else None,
        }
        model_prob={
            "ML":probs.home_ml,
            "SPREAD":probs.home_spread,
            "TOTAL":probs.over,
        }
        sharp=row.get("pinnacle_entry_probability") or {}
        used=False
        for market in ("ML","SPREAD","TOTAL"):
            if labels[market] is None or sharp.get(market) is None:
                continue
            value=float(sharp[market])
            if not 0.0<=value<=1.0:
                raise ValueError("historical Pinnacle probability outside [0,1]")
            sharp_pairs[market].append((value,int(labels[market])))
            model_pairs[market].append((float(model_prob[market]),int(labels[market])))
            ages[market].append(float(row.get("snapshot_age_minutes") or 0.0))
            used=True
        if used:
            resolved_keys.append(str(row.get("entry_key")))

    markets={}
    for market in ("ML","SPREAD","TOTAL"):
        sharp_score=_proper(sharp_pairs[market])
        model_score=_proper(model_pairs[market])
        markets[market]={
            "n":sharp_score["n"],
            "pinnacle_brier":sharp_score["brier"],
            "pinnacle_logloss":sharp_score["logloss"],
            "pinnacle_ece":sharp_score["ece"],
            "model_brier_paired":model_score["brier"],
            "model_logloss_paired":model_score["logloss"],
            "model_ece_paired":model_score["ece"],
            "mean_snapshot_age_minutes":(
                sum(ages[market])/len(ages[market]) if ages[market] else None
            ),
            "role":"HISTORICAL_EVALUATION_ONLY",
            "used_for_certification":False,
        }

    report={
        "schema":"pulsar-nba-historical-pinnacle-performance-v1",
        "role":"HISTORICAL_EVALUATION_ONLY",
        "resolved_recovery_rows":len(set(resolved_keys)),
        "markets":markets,
        "market_data_used_as_model_feature":False,
        "used_for_certification":False,
        "pinnacle_replacement":False,
        "betting_certified":False,
    }
    target=Path(output_path);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2,sort_keys=True),encoding="utf-8")
    return report


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--forecasts",default="runtime/evidence/final_forecasts.jsonl")
    p.add_argument("--outcomes",default="runtime/evidence/final_outcomes.jsonl")
    p.add_argument("--recovery",default="runtime/research/pinnacle_historical_entry.jsonl")
    p.add_argument("--output",default="runtime/research/pinnacle_historical_performance.json")
    a=p.parse_args()
    print(json.dumps(evaluate(
        forecasts_path=a.forecasts,outcomes_path=a.outcomes,
        recovery_path=a.recovery,output_path=a.output),indent=2))


if __name__=="__main__":
    main()
