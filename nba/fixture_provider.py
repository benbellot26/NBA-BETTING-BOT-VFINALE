"""Deterministic synthetic provider used only by tests and CI dry-runs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .provider_contract import ProviderSnapshot, snapshot_from_parts
from .schedule import ScheduleGame
from .teams import team_info


@dataclass
class DeterministicFixtureProvider:
    provider_id: str = "ci-deterministic-fixture"

    def capture(self, *, target_date: str) -> ProviderSnapshot:
        home, away = "Boston Celtics", "New York Knicks"
        captured = f"{target_date}T22:00:00+00:00"
        tip = f"{target_date}T22:20:00+00:00"
        prior = f"{target_date}T20:00:00+00:00"
        schedule = [ScheduleGame(
            "fixture-game", target_date, tip, home, away, 1, "Scheduled")]
        advanced = [
            {"TEAM_NAME": home, "OFF_RATING": 118.0, "DEF_RATING": 111.0,
             "PACE": 99.0, "EFG_PCT": .57, "TM_TOV_PCT": 12.5,
             "OREB_PCT": .27, "GP": 12},
            {"TEAM_NAME": away, "OFF_RATING": 115.0, "DEF_RATING": 114.0,
             "PACE": 98.0, "EFG_PCT": .55, "TM_TOV_PCT": 13.0,
             "OREB_PCT": .25, "GP": 12},
        ]
        base = [
            {"TEAM_NAME": home, "FGA": 89, "FG3A": 39, "FTA": 22},
            {"TEAM_NAME": away, "FGA": 88, "FG3A": 36, "FTA": 21},
        ]
        players = []
        advanced_players = []
        for team in (home, away):
            tid = team_info(team).team_id
            prefix = "BOS" if team == home else "NYK"
            for index in range(8):
                pid = tid * 100 + index
                name = f"{prefix} Player {index}"
                players.append({
                    "TEAM_ID": tid, "PLAYER_ID": pid,
                    "PLAYER_NAME": name, "MIN": 30.0,
                })
                advanced_players.append({
                    "TEAM_ID": tid, "PLAYER_ID": pid,
                    "PLAYER_NAME": name,
                    "OFF_RATING": 116 + (index % 3),
                    "DEF_RATING": 113 - (index % 2),
                    "USG_PCT": .20 + index * .005,
                })
        stats = {
            "season": "2026-27", "date_to": "11/14/2026",
            "observed_at": prior,
            "advanced_windows": {
                0: advanced, 30: advanced, 15: advanced,
                10: advanced, 5: advanced,
            },
            "base_season": base,
            "player_season": players,
            "player_recent": players,
            "player_advanced": advanced_players,
            "snapshot": {
                "sha256": "a" * 64, "observed_at": prior,
                "source": "ci-fixture",
            },
        }
        injuries = {
            "reported_at": f"{target_date}T21:50:00+00:00",
            "source_url": "fixture://official-injury-report",
            "records": [],
            "team_status": {
                f"{target_date}|{home}": "SUBMITTED",
                f"{target_date}|{away}": "SUBMITTED",
            },
        }
        # Keep fixture date intentionally fixed so its stat cutoff is deterministic.
        if target_date != "2026-11-15":
            raise ValueError("deterministic CI fixture supports 2026-11-15 only")
        return snapshot_from_parts(
            target_date=target_date, captured_at=captured,
            provider_id=self.provider_id, schedule=schedule,
            stats=stats, injuries=injuries, role="SYNTHETIC_CI_ONLY",
        )
