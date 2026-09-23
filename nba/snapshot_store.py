from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")


def persist_snapshot(root: str|Path, *, kind: str, observed_at: str, payload: Any, source: str) -> dict[str,Any]:
    data=canonical_bytes(payload); digest=hashlib.sha256(data).hexdigest()
    stamp=observed_at.replace(":","").replace("-","").replace("+","_").replace("T","_")
    target=Path(root)/kind/f"{stamp}_{digest[:12]}.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists(): target.write_bytes(data)
    return {"kind":kind,"path":str(target),"sha256":digest,"observed_at":observed_at,"source":source,"bytes":len(data)}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
