from __future__ import annotations

from datetime import datetime,timezone
import json
from pathlib import Path
from typing import Any

REQUIRED=("game_id","market","selection","price","model_probability","lower_probability","entry_at")

def append_entry(path:str|Path,row:dict[str,Any])->None:
    missing=[k for k in REQUIRED if row.get(k) is None]
    if str(row.get("market") or "").upper()!="ML" and row.get("line") is None:missing.append("line")
    if missing:raise ValueError(f"paper entry missing: {', '.join(missing)}")
    payload=dict(row);payload["ledger_role"]="PAPER";payload["recorded_at"]=datetime.now(timezone.utc).isoformat()
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("a",encoding="utf-8") as fh:fh.write(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n")
