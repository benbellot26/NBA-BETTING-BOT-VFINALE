from __future__ import annotations

import math
from typing import Iterable


def brier(probability: float, outcome: int) -> float:
    return (float(probability)-int(outcome))**2


def logloss(probability: float, outcome: int, eps: float = 1e-12) -> float:
    p = max(eps, min(1-eps, float(probability)))
    y = int(outcome)
    return -(y*math.log(p)+(1-y)*math.log(1-p))


def calibration_ece(rows: Iterable[tuple[float,int]], bins: int = 10) -> float:
    data = list(rows)
    if not data: return 0.0
    total = len(data); ece = 0.0
    for i in range(bins):
        lo=i/bins; hi=(i+1)/bins
        cell=[(p,y) for p,y in data if lo <= p < hi or (i==bins-1 and p==1)]
        if not cell: continue
        avg_p=sum(p for p,_ in cell)/len(cell); avg_y=sum(y for _,y in cell)/len(cell)
        ece += len(cell)/total*abs(avg_p-avg_y)
    return ece


def mae(predicted: Iterable[float], actual: Iterable[float]) -> float:
    pairs=list(zip(predicted,actual))
    return sum(abs(a-b) for a,b in pairs)/len(pairs) if pairs else 0.0
