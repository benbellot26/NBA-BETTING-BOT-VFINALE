from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def append_jsonl(path: str | Path, row: dict[str, Any]) -> None:
    target=Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    payload=dict(row); payload.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True, separators=(",",":"))+"\n")


def clv_probability(entry_price: float, close_price: float) -> float:
    return 100.0*((1.0/close_price)-(1.0/entry_price))


def line_clv(entry_line: float, close_line: float, *, side: str) -> float:
    if side.lower() in {"home","over"}:
        return float(entry_line)-float(close_line) if side.lower()=="home" else float(close_line)-float(entry_line)
    return float(close_line)-float(entry_line) if side.lower()=="away" else float(entry_line)-float(close_line)
