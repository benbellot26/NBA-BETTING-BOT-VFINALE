from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

VALID_STATUSES={"AVAILABLE","PROBABLE","QUESTIONABLE","DOUBTFUL","OUT"}


def _dt(value: str) -> datetime:
    out=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if out.tzinfo is None: out=out.replace(tzinfo=timezone.utc)
    return out.astimezone(timezone.utc)


@dataclass(frozen=True)
class InjuryRecord:
    player_id: str
    player_name: str
    team: str
    status: str
    reported_at: str
    reason: str = ""

    def validated(self) -> "InjuryRecord":
        if self.status.upper() not in VALID_STATUSES: raise ValueError(f"unsupported status {self.status}")
        _dt(self.reported_at)
        return self


def latest_point_in_time(records: Iterable[InjuryRecord], *, cutoff: str) -> dict[str, InjuryRecord]:
    cutoff_dt=_dt(cutoff); latest={}
    for row in records:
        row=row.validated(); dt=_dt(row.reported_at)
        if dt>cutoff_dt: continue
        current=latest.get(row.player_id)
        if current is None or _dt(current.reported_at)<dt: latest[row.player_id]=row
    return latest
