"""Stable provider boundary between acquisition and the basketball model."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Protocol

from .live_inputs import prior_day_cutoff
from .schedule import ScheduleGame, games_on, season_for_date

SCHEMA = "pulsar-nba-provider-snapshot-v1"


class NoGamesOnTargetDate(ValueError):
    """No scheduled game on the requested NBA date; do not fetch paid data."""


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("provider timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _sha(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ProviderSnapshot:
    target_date: str
    season: str
    captured_at: str
    provider_id: str
    schedule: list[dict[str, Any]]
    stats: dict[str, Any]
    injuries: dict[str, Any]
    role: str = "RESEARCH_INPUT"
    schema: str = SCHEMA

    def validated(self) -> "ProviderSnapshot":
        if self.schema != SCHEMA:
            raise ValueError("unsupported provider snapshot schema")
        if not self.provider_id.strip():
            raise ValueError("provider_id is required")
        if self.season != season_for_date(self.target_date):
            raise ValueError("provider snapshot season mismatch")
        captured = _dt(self.captured_at)
        if self.stats.get("season") != self.season:
            raise ValueError("stat-pack season mismatch")
        if self.stats.get("date_to") != prior_day_cutoff(self.target_date):
            raise ValueError("stat-pack PIT cutoff mismatch")
        if _dt(str(self.stats["observed_at"])) > captured:
            raise ValueError("stats observed after provider capture")
        if _dt(str(self.injuries["reported_at"])) > captured:
            raise ValueError("injuries reported after provider capture")
        schedule = [ScheduleGame(**row) for row in self.schedule]
        slate = games_on(schedule, self.target_date)
        if not slate:
            raise NoGamesOnTargetDate("provider snapshot has no target-date games")
        if not any(_dt(game.commence_time) > captured for game in slate):
            raise ValueError("provider snapshot has no upcoming target-date games")
        return self

    def fingerprint(self) -> str:
        payload = asdict(self)
        return _sha(payload)


class DataProvider(Protocol):
    provider_id: str

    def capture(self, *, target_date: str) -> ProviderSnapshot:
        ...


def snapshot_from_parts(
    *, target_date: str, captured_at: str, provider_id: str,
    schedule: list[ScheduleGame], stats: dict[str, Any],
    injuries: dict[str, Any], role: str = "RESEARCH_INPUT",
) -> ProviderSnapshot:
    snapshot = ProviderSnapshot(
        target_date=target_date,
        season=season_for_date(target_date),
        captured_at=captured_at,
        provider_id=provider_id,
        schedule=[asdict(game) for game in schedule],
        stats=stats,
        injuries=injuries,
        role=role,
    )
    return snapshot.validated()
