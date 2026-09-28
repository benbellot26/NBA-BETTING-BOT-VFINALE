import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nba.historical_pinnacle_recovery import recover


class HistoricalRecoveryAccessGateTests(unittest.TestCase):
    def test_free_plan_probe_skips_before_budget_or_network(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            probe=root/"probe.json"
            budget=root/"budget.json"
            forecasts=root/"forecasts.jsonl"
            probe.write_text(json.dumps({
                "state":"HISTORICAL_PROVIDER_ERROR",
                "provider_error_code":"HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN",
            }),encoding="utf-8")
            forecasts.write_text(json.dumps({
                "role":"PIT_FINAL_FORECAST",
                "entry_key":"g|v1|FINAL",
                "forecast_at":"2026-10-20T20:00:00+00:00",
            })+"\n",encoding="utf-8")
            with patch(
                "nba.historical_pinnacle_recovery.reserve_odds_request"
            ) as reserve, patch(
                "nba.historical_pinnacle_recovery.fetch_historical_nba_odds"
            ) as fetch:
                result=recover(
                    forecasts_path=str(forecasts),
                    output_path=str(root/"out.jsonl"),
                    budget_path=str(budget),
                    access_probe_path=str(probe),
                    max_snapshots=4,
                )
            reserve.assert_not_called()
            fetch.assert_not_called()
            self.assertEqual(result["status"],"SKIPPED_ACCESS_BLOCKED")
            self.assertEqual(result["odds_api_requests"],0)
            self.assertEqual(
                result["provider_error_code"],
                "HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN",
            )
            self.assertFalse(budget.exists())


if __name__=="__main__":
    unittest.main()
