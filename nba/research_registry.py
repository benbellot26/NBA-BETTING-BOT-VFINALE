from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


def fingerprint(spec: dict[str, Any]) -> str:
    raw=json.dumps(spec,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def register(path: str | Path, *, experiment_id: str, hypothesis: str, spec: dict[str, Any], train_period: str, validation_period: str, primary_metric: str, success_rule: str, minimum_sample: int, stopping_rule: str, promotion_scope: str) -> dict[str, Any]:
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    existing=[]
    if target.exists():
        existing=[json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(row.get("experiment_id")==experiment_id for row in existing):
        raise ValueError("experiment_id already registered; registrations are append-only")
    row={"experiment_id":experiment_id,"registered_at":datetime.now(timezone.utc).isoformat(),"hypothesis":hypothesis,"spec":spec,"spec_fingerprint":fingerprint(spec),"train_period":train_period,"validation_period":validation_period,"primary_metric":primary_metric,"success_rule":success_rule,"minimum_sample":int(minimum_sample),"stopping_rule":stopping_rule,"promotion_scope":promotion_scope}
    with target.open("a",encoding="utf-8") as fh: fh.write(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n")
    return row
