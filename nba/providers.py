"""Concrete data providers implementing the stable provider contract."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

from .injury_pdf import fetch_latest_report
from .live_inputs import acquire_stat_pack
from .provider_contract import DataProvider, ProviderSnapshot, NoGamesOnTargetDate, snapshot_from_parts
from .schedule import ScheduleGame, fetch_schedule, games_on, season_for_date


@dataclass
class OfficialNBAProvider:
    """Current official endpoints. Fails closed when GitHub runners are blocked."""
    snapshot_root: str = "runtime/snapshots"
    provider_id: str = "official-nba"

    def capture(self, *, target_date: str) -> ProviderSnapshot:
        season = season_for_date(target_date)
        schedule = fetch_schedule()
        slate = games_on(schedule, target_date)
        if not slate:
            raise NoGamesOnTargetDate("no NBA games on target date")
        # Avoid waiting for stats/PDF after the last target match has tipped.
        current = datetime.now(timezone.utc)
        if not any(
            datetime.fromisoformat(game.commence_time.replace("Z", "+00:00"))
            .astimezone(timezone.utc) > current for game in slate
        ):
            raise NoGamesOnTargetDate("no upcoming NBA games on target date")
        stats_observed_at = datetime.now(timezone.utc).isoformat()
        stats = acquire_stat_pack(
            season=season, observed_at=stats_observed_at, game_date=target_date,
            snapshot_root=self.snapshot_root,
        )
        injuries = fetch_latest_report(season=season)
        # Capture time is AFTER the last provider response, never at the start
        # of a possibly slow request chain. Finished games are ignored later.
        captured_at = datetime.now(timezone.utc).isoformat()
        return snapshot_from_parts(
            target_date=target_date, captured_at=captured_at,
            provider_id=self.provider_id, schedule=schedule,
            stats=stats, injuries=injuries, role="PROSPECTIVE_SOURCE",
        )


@dataclass
class BundleProvider:
    """Unverified local bundle, intentionally research-only."""
    path: str
    provider_id: str = "local-unverified-bundle"

    def capture(self, *, target_date: str) -> ProviderSnapshot:
        # Local import prevents a cycle when live_runtime imports OfficialNBAProvider.
        from .pit_bundle import load as load_bundle
        bundle = load_bundle(self.path)
        if bundle["target_date"] != target_date:
            raise ValueError("bundle target date differs from requested date")
        return snapshot_from_parts(
            target_date=target_date, captured_at=bundle["captured_at"],
            provider_id=self.provider_id,
            schedule=[ScheduleGame(**row) for row in bundle["schedule"]],
            stats=bundle["stats"], injuries=bundle["injuries"],
            role="UNVERIFIED_OFFLINE_RESEARCH",
        )


@dataclass
class JsonSnapshotProvider:
    """Generic research adapter for schema-compatible provider snapshots."""
    path: str
    provider_id: str = "json-snapshot"

    def capture(self, *, target_date: str) -> ProviderSnapshot:
        payload = json.loads(Path(self.path).read_text(encoding="utf-8"))
        # JSON is never an authority source, even when its editable role or
        # provider_id fields claim to be an official prospective feed.
        payload["role"] = "UNVERIFIED_OFFLINE_RESEARCH"
        payload["provider_id"] = self.provider_id
        snapshot = ProviderSnapshot(**payload).validated()
        if snapshot.target_date != target_date:
            raise ValueError("snapshot target date differs from requested date")
        return snapshot
