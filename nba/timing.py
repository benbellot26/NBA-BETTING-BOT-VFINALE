from __future__ import annotations

from datetime import datetime, timezone

FINAL_MIN_MINUTES_TO_GAME = 5.0
FINAL_MAX_MINUTES_TO_GAME = 30.0


def _dt(value: str) -> datetime:
    out=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if out.tzinfo is None: out=out.replace(tzinfo=timezone.utc)
    return out.astimezone(timezone.utc)


def minutes_to_tip(*, analyzed_at: str, commence_time: str) -> float:
    return (_dt(commence_time)-_dt(analyzed_at)).total_seconds()/60.0


def is_final_window(*, phase: str, analyzed_at: str, commence_time: str) -> bool:
    m=minutes_to_tip(analyzed_at=analyzed_at,commence_time=commence_time)
    return str(phase).upper()=="FINAL" and FINAL_MIN_MINUTES_TO_GAME <= m <= FINAL_MAX_MINUTES_TO_GAME
