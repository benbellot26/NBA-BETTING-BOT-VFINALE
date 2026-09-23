from __future__ import annotations

from typing import Any, Callable, Iterable

from .performance import brier, logloss, mae, calibration_ece


def chronological_evaluate(rows: Iterable[dict[str,Any]], predictor: Callable[[dict[str,Any]],dict[str,float]]) -> dict[str,Any]:
    ordered=sorted(rows,key=lambda r:(str(r["game_date"]),str(r["game_id"])))
    ml=[]; margins_pred=[]; margins_real=[]; totals_pred=[]; totals_real=[]
    for row in ordered:
        pred=predictor(row); y=1 if float(row["home_score"])>float(row["away_score"]) else 0
        ml.append((float(pred["home_ml"]),y)); margins_pred.append(float(pred["margin_mean"])); margins_real.append(float(row["home_score"])-float(row["away_score"])); totals_pred.append(float(pred["total_mean"])); totals_real.append(float(row["home_score"])+float(row["away_score"]))
    n=len(ordered)
    return {"n":n,"ml_brier":sum(brier(p,y) for p,y in ml)/n if n else 0.0,"ml_logloss":sum(logloss(p,y) for p,y in ml)/n if n else 0.0,"ml_ece":calibration_ece(ml),"margin_mae":mae(margins_pred,margins_real),"total_mae":mae(totals_pred,totals_real)}
