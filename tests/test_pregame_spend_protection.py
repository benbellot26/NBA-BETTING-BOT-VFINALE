import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from nba.fixture_provider import DeterministicFixtureProvider
from nba.live_runtime import run
from nba.odds_budget import OddsBudgetExceeded, reserve, status


class PregameSpendProtectionTests(unittest.TestCase):
    def test_regular_skips_odds_with_zero_completed_team_games(self):
        fixture = DeterministicFixtureProvider().capture(target_date="2026-11-15")
        stats = dict(fixture.stats)
        windows = {}
        for key, rows in stats["advanced_windows"].items():
            windows[key] = [{**row, "GP": 0} for row in rows]
        stats["advanced_windows"] = windows
        source = replace(fixture, stats=stats, provider_id="official-nba",
                         role="PROSPECTIVE_SOURCE")
        with tempfile.TemporaryDirectory() as folder, patch(
            "nba.live_runtime.OfficialNBAProvider.capture", return_value=source
        ), patch("nba.live_runtime.fetch_nba_odds") as fetch:
            root = Path(folder)
            result = run(
                target_date="2026-11-15", output=str(root/"run.json"),
                snapshot_root=str(root/"snapshots"),
                paper_path=str(root/"paper.jsonl"),
                forecasts_path=str(root/"forecasts.jsonl"),
                odds_budget_path=str(root/"odds_budget.json"),
                operating_mode="regular",
            )
            self.assertEqual(result["status"], "NO_ANALYSIS")
            self.assertEqual(result["odds_api_requests"], 0)
            self.assertTrue(any("five_completed" in error for error in result["failures"]))
            self.assertFalse((root/"odds_budget.json").exists())
            fetch.assert_not_called()

    def test_corrupt_budget_does_not_reset_on_next_request(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"odds_budget.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(OddsBudgetExceeded, "unreadable"):
                reserve(path=path, purpose="market_smoke")

    def test_invalid_budget_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"odds_budget.json"
            path.write_text(json.dumps({"schema":"anything", "used":0,"purposes":{},"utc_date":"2026-09-23"}))
            with self.assertRaisesRegex(OddsBudgetExceeded,"invalid"):
                reserve(path=path,purpose="market_smoke")


if __name__=="__main__":
    unittest.main()
