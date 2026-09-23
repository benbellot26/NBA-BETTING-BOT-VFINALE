from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_jsonl(path: str | Path) -> list[dict[str,Any]]:
    target=Path(path)
    if not target.exists(): return []
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(*, predictions_path: str|Path, paper_path: str|Path) -> dict[str,Any]:
    predictions=_read_jsonl(predictions_path); paper=_read_jsonl(paper_path)
    bets=[r for r in paper if r.get("status")=="BET" or r.get("ledger_role")=="PAPER"]
    clv=[float(r["clv_pp"]) for r in paper if r.get("clv_pp") is not None]
    return {"predictions":len(predictions),"paper_entries":len(bets),"clv_n":len(clv),"mean_clv_pp":sum(clv)/len(clv) if clv else None,"positive_clv_rate":sum(1 for x in clv if x>0)/len(clv) if clv else None}
