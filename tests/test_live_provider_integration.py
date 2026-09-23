import json
import tempfile
import unittest
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from nba.fixture_provider import DeterministicFixtureProvider
from nba.live_runtime import run
from nba.provider_contract import NoGamesOnTargetDate
from nba.schedule import ScheduleGame


DATE = "2026-11-15"
AT = datetime.fromisoformat("2026-11-15T22:00:00+00:00")


def fixture_odds():
    return [{
        "id": "odds-fixture", "home_team": "Boston Celtics",
        "away_team": "New York Knicks",
        "commence_time": "2026-11-15T22:20:00Z",
        "bookmakers": [{
            "key": "pinnacle", "last_update": "2026-11-15T21:59:00Z",
            "markets": [
                {"key": "h2h", "last_update": "2026-11-15T21:59:00Z",
                 "outcomes": [
                     {"name": "Boston Celtics", "price": 1.91},
                     {"name": "New York Knicks", "price": 1.99}]},
                {"key": "spreads", "last_update": "2026-11-15T21:59:00Z",
                 "outcomes": [
                     {"name": "Boston Celtics", "point": -3.5, "price": 1.91},
                     {"name": "New York Knicks", "point": 3.5, "price": 1.91}]},
                {"key": "totals", "last_update": "2026-11-15T21:59:00Z",
                 "outcomes": [
                     {"name": "Over", "point": 226.5, "price": 1.91},
                     {"name": "Under", "point": 226.5, "price": 1.91}]},
            ],
        }],
    }]


def params(root):
    base = Path(root)
    return dict(
        target_date=DATE, output=str(base / "analysis.json"),
        snapshot_root=str(base / "snapshots"),
        paper_path=str(base / "paper.jsonl"),
        forecasts_path=str(base / "forecasts.jsonl"),
        certification_path=str(base / "uncertified.json"),
    )


class LiveProviderIntegrationTests(unittest.TestCase):
    def test_full_official_provider_path_with_fixture_remains_uncertified(self):
        fixture = DeterministicFixtureProvider().capture(target_date=DATE)
        official_shape = replace(fixture, provider_id="official-nba",
                                 role="PROSPECTIVE_SOURCE")
        with tempfile.TemporaryDirectory() as directory, patch(
            "nba.live_runtime.OfficialNBAProvider.capture", return_value=official_shape
        ), patch("nba.live_runtime.fetch_nba_odds", return_value=fixture_odds()) as odds, patch(
            "nba.live_runtime.datetime", wraps=datetime
        ) as clock:
            clock.now.return_value = AT
            output = run(**params(directory))
            self.assertEqual(output["status"], "OK", output["failures"])
            self.assertEqual(len(output["games"]), 1)
            self.assertEqual(len(output["games"][0]["decision"]["candidates"]), 6)
            self.assertTrue(all(candidate["status"] == "NO_BET"
                                for candidate in output["games"][0]["decision"]["candidates"]))
            self.assertEqual(output["final_forecasts"]["added"], 1)
            self.assertTrue(Path(directory, "forecasts.jsonl").exists())
            odds.assert_called_once()

    def test_no_games_does_not_fetch_odds(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "nba.live_runtime.OfficialNBAProvider.capture",
            side_effect=NoGamesOnTargetDate("no games")
        ), patch("nba.live_runtime.fetch_nba_odds") as odds:
            output = run(**params(directory))
            self.assertEqual(output["status"], "NO_GAMES")
            odds.assert_not_called()

    def test_provider_failure_does_not_spend_odds(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "nba.live_runtime.OfficialNBAProvider.capture",
            side_effect=RuntimeError("stats unavailable")
        ), patch("nba.live_runtime.fetch_nba_odds") as odds:
            output = run(**params(directory))
            self.assertEqual(output["status"], "NO_ANALYSIS")
            self.assertIn("official_provider:stats unavailable", output["failures"])
            odds.assert_not_called()

    def test_untrusted_provider_role_is_rejected_before_odds(self):
        fixture = DeterministicFixtureProvider().capture(target_date=DATE)
        with tempfile.TemporaryDirectory() as directory, patch(
            "nba.live_runtime.OfficialNBAProvider.capture", return_value=fixture
        ), patch("nba.live_runtime.fetch_nba_odds") as odds:
            output = run(**params(directory))
            self.assertEqual(output["status"], "NO_ANALYSIS")
            odds.assert_not_called()

    def test_started_early_game_does_not_block_upcoming_game(self):
        fixture = DeterministicFixtureProvider().capture(target_date=DATE)
        early = ScheduleGame(
            "early", DATE, "2026-11-15T21:30:00Z", "Miami Heat",
            "Toronto Raptors", 2, "Live")
        mixed = replace(fixture, provider_id="official-nba", role="PROSPECTIVE_SOURCE",
                        schedule=[asdict(early)] + fixture.schedule)
        with tempfile.TemporaryDirectory() as directory, patch(
            "nba.live_runtime.OfficialNBAProvider.capture", return_value=mixed
        ), patch("nba.live_runtime.fetch_nba_odds", return_value=fixture_odds()), patch(
            "nba.live_runtime.datetime", wraps=datetime
        ) as clock:
            clock.now.return_value = AT
            output = run(**params(directory))
            self.assertEqual([game["game_id"] for game in output["games"]], ["fixture-game"])
            self.assertFalse(any("early" in f for f in output["failures"]))


if __name__ == "__main__":
    unittest.main()
