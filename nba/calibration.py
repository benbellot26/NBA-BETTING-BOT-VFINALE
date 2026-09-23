from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class BinCell:
    lower: float
    upper: float
    n: int
    mean_prediction: float
    observed_rate: float


def reliability(rows: Iterable[tuple[float,int]], *, bins: int=10) -> list[BinCell]:
    data=[(float(p),int(y)) for p,y in rows]
    out=[]
    for i in range(bins):
        lo=i/bins; hi=(i+1)/bins
        cell=[(p,y) for p,y in data if lo<=p<hi or (i==bins-1 and p==1.0)]
        if not cell: continue
        out.append(BinCell(lo,hi,len(cell),sum(p for p,_ in cell)/len(cell),sum(y for _,y in cell)/len(cell)))
    return out


def calibrate_probability(p: float, cells: list[BinCell], *, minimum_cell_n: int=50) -> tuple[float,bool]:
    p=float(p)
    for cell in cells:
        if cell.lower<=p<cell.upper or (p==1.0 and cell.upper==1.0):
            if cell.n<minimum_cell_n: return p,False
            shrink=min(1.0,cell.n/250.0)
            calibrated=(1-shrink)*p+shrink*cell.observed_rate
            return max(.001,min(.999,calibrated)),True
    return p,False
