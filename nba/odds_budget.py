"""Persistent fail-closed request budget for paid Odds API calls."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_DAILY_LIMIT = 48

class OddsBudgetExceeded(RuntimeError):
    pass

def _limit(value: int | None = None) -> int:
    raw = value if value is not None else int(os.environ.get("NBA_ODDS_DAILY_REQUEST_BUDGET", DEFAULT_DAILY_LIMIT))
    if raw < 1:
        raise ValueError("Odds API daily request budget must be positive")
    return raw

def _read(path: Path, day: str, limit: int) -> dict[str, Any]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            raise OddsBudgetExceeded("Odds API budget ledger unreadable; fail closed") from None
        if (not isinstance(data, dict)
                or data.get("schema") != "pulsar-nba-odds-budget-v1"
                or not isinstance(data.get("used"), int)
                or isinstance(data.get("used"), bool)
                or data["used"] < 0
                or not isinstance(data.get("purposes"), dict)):
            raise OddsBudgetExceeded("Odds API budget ledger invalid; fail closed")
        if data.get("utc_date") == day and data["used"] > limit:
            raise OddsBudgetExceeded("Odds API budget already exceeds configured limit")
    else:
        data = {}
    if data.get("utc_date") != day:
        data = {"schema":"pulsar-nba-odds-budget-v1","utc_date":day,
                "used":0,"purposes":{}}
    data["limit"] = limit
    return data

def reserve(*, path: str | Path = "runtime/odds_budget.json", purpose: str,
            limit: int | None = None, now: datetime | None = None) -> dict[str, Any]:
    current=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cap=_limit(limit); target=Path(path); day=current.date().isoformat()
    state=_read(target,day,cap)
    used=int(state.get("used") or 0)
    if used >= cap:
        raise OddsBudgetExceeded(f"Odds API daily request budget exhausted ({used}/{cap})")
    state["used"]=used+1
    purposes=dict(state.get("purposes") or {})
    purposes[purpose]=int(purposes.get(purpose) or 0)+1
    state["purposes"]=purposes
    state["remaining"]=cap-state["used"]
    state["updated_at"]=current.isoformat()
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix(target.suffix+".tmp")
    temp.write_text(json.dumps(state,indent=2,sort_keys=True),encoding="utf-8")
    temp.replace(target)
    return state

def status(*, path: str | Path = "runtime/odds_budget.json",
           limit: int | None = None, now: datetime | None = None) -> dict[str, Any]:
    current=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cap=_limit(limit); target=Path(path)
    state=_read(target,current.date().isoformat(),cap)
    state["remaining"]=cap-int(state.get("used") or 0)
    return state
