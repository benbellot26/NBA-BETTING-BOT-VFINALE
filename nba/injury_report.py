from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

VALID_STATUSES = {"AVAILABLE", "PROBABLE", "QUESTIONABLE", "DOUBTFUL", "OUT"}


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("report timestamps must include timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class InjuryRecord:
    player_id: str
    player_name: str
    team: str
    status: str
    reported_at: str
    reason: str = ""
    game_date: str = ""
    matchup: str = ""

    def validated(self) -> "InjuryRecord":
        if self.status.upper() not in VALID_STATUSES:
            raise ValueError(f"unsupported status {self.status}")
        _dt(self.reported_at)
        return self


def latest_point_in_time(records: Iterable[InjuryRecord], *, cutoff: str) -> dict[str, InjuryRecord]:
    cutoff_dt = _dt(cutoff)
    latest: dict[str, InjuryRecord] = {}
    for row in records:
        row = row.validated()
        at = _dt(row.reported_at)
        if at > cutoff_dt:
            continue
        key = f"{row.team}|{row.player_id}|{row.game_date}"
        current = latest.get(key)
        if current is None or _dt(current.reported_at) < at:
            latest[key] = row
    return latest
