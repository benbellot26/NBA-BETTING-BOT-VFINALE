import json
import tempfile
import unittest
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from nba.fixture_provider import DeterministicFixtureProvider
from nba.provider_contract import NoGamesOnTargetDate, ProviderSnapshot
from nba.providers import JsonSnapshotProvider, OfficialNBAProvider
from nba.schedule import ScheduleGame


class ProviderBoundaryTests(unittest.TestCase):
    def test_json_input_cannot_claim_live_authority(self):
        fixture = DeterministicFixtureProvider().capture(target_date="2026-11-15")
        payload = asdict(fixture)
        payload["role"] = "PROSPECTIVE_SOURCE"
        payload["provider_id"] = "official-nba"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            snapshot = JsonSnapshotProvider(str(path)).capture(target_date="2026-11-15")
        self.assertEqual(snapshot.role, "UNVERIFIED_OFFLINE_RESEARCH")
        self.assertEqual(snapshot.provider_id, "json-snapshot")

    def test_mixed_started_and_upcoming_games_are_allowed(self):
        fixture = DeterministicFixtureProvider().capture(target_date="2026-11-15")
        early = ScheduleGame("early", "2026-11-15", "2026-11-15T21:30:00Z",
                             "Miami Heat", "Toronto Raptors", 2, "Live")
        mixed = replace(fixture, schedule=[asdict(early)] + fixture.schedule)
        self.assertEqual(len(mixed.validated().schedule), 2)

    def test_all_started_games_are_rejected(self):
        fixture = DeterministicFixtureProvider().capture(target_date="2026-11-15")
        prior = ScheduleGame("early", "2026-11-15", "2026-11-15T21:30:00Z",
                             "Miami Heat", "Toronto Raptors", 2, "Live")
        with self.assertRaisesRegex(ValueError, "no upcoming"):
            replace(fixture, schedule=[asdict(prior)]).validated()

    def test_official_provider_uses_communications_schedule_when_cdn_blocked(self):
        fixture = DeterministicFixtureProvider().capture(target_date="2026-11-15")
        fallback = [ScheduleGame(
            "nba-pr-2026-27-2026-11-15-100", "2026-11-15",
            "2026-11-15T22:20:00Z", "Boston Celtics", "New York Knicks",
            1, "Scheduled - NBA Communications",
        )]
        with patch("nba.providers.fetch_schedule", side_effect=RuntimeError("HTTP 403")), patch(
            "nba.providers.fetch_pregame_schedule", return_value=fallback
        ) as communications, patch(
            "nba.providers.acquire_stat_pack", return_value=fixture.stats
        ), patch(
            "nba.providers.fetch_latest_report", return_value=fixture.injuries
        ), patch("nba.providers.datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime.fromisoformat("2026-11-15T22:00:00+00:00")
            snapshot = OfficialNBAProvider().capture(target_date="2026-11-15")
        self.assertEqual(snapshot.schedule[0]["game_id"], fallback[0].game_id)
        communications.assert_called_once_with(
            season="2026-27", target_date="2026-11-15"
        )

    def test_official_provider_does_not_fetch_stats_if_no_games(self):
        with patch("nba.providers.fetch_schedule", return_value=[]), patch(
            "nba.providers.acquire_stat_pack") as stats, patch(
                "nba.providers.fetch_latest_report") as injuries:
            with self.assertRaises(NoGamesOnTargetDate):
                OfficialNBAProvider().capture(target_date="2026-11-15")
        stats.assert_not_called()
        injuries.assert_not_called()


if __name__ == "__main__":
    unittest.main()
