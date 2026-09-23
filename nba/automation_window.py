"""Validate that the broad UTC Actions window covers typical NBA tip times across DST."""
from __future__ import annotations
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

ACTIVE_UTC_HOURS = set(range(17, 24)) | set(range(0, 7))
ET = ZoneInfo("America/New_York")


def utc_hour_for_et(*, local_date: str, local_tip: str) -> int:
    day = datetime.fromisoformat(local_date).date()
    hh, mm = (int(x) for x in local_tip.split(":"))
    local = datetime.combine(day, time(hh, mm), tzinfo=ET)
    return local.astimezone(timezone.utc).hour


def covered(*, local_date: str, local_tip: str) -> bool:
    return utc_hour_for_et(local_date=local_date, local_tip=local_tip) in ACTIVE_UTC_HOURS


def representative_checks() -> dict[str, bool]:
    cases = {
        "winter_1900": ("2026-12-15", "19:00"),
        "winter_2230": ("2026-12-15", "22:30"),
        "summer_1900": ("2026-10-10", "19:00"),
        "summer_2230": ("2026-10-10", "22:30"),
        "spring_1900": ("2027-03-15", "19:00"),
        "spring_2230": ("2027-03-15", "22:30"),
    }
    return {name: covered(local_date=d, local_tip=t) for name, (d, t) in cases.items()}
