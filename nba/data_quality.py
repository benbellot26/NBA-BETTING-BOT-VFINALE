from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _dt(value: str | None) -> datetime | None:
    if not value: return None
    try:
        out=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if out.tzinfo is None: out=out.replace(tzinfo=timezone.utc)
        return out.astimezone(timezone.utc)
    except Exception:
        return None


def assess(*, analyzed_at: str, team_stats_at: str | None, injury_report_at: str | None, odds_at: str | None, home_rotation_minutes: float | None = None, away_rotation_minutes: float | None = None) -> dict[str, Any]:
    now=_dt(analyzed_at)
    failures=[]; ages={}
    if now is None: return {"eligible":False,"failures":["invalid_analyzed_at"],"ages_minutes":{}}
    for label,value,max_age in (("team_stats",team_stats_at,1440),("injury_report",injury_report_at,360),("odds",odds_at,15)):
        dt=_dt(value)
        if dt is None:
            failures.append(f"{label}_timestamp_missing"); continue
        age=(now-dt).total_seconds()/60.0; ages[label]=age
        if age < -2: failures.append(f"{label}_timestamp_in_future")
        if age > max_age: failures.append(f"{label}_stale")
    for side,total in (("home",home_rotation_minutes),("away",away_rotation_minutes)):
        if total is not None and abs(float(total)-240.0)>.75: failures.append(f"{side}_rotation_not_240")
    return {"eligible":not failures,"failures":failures,"ages_minutes":ages}
