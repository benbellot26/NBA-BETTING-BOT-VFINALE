import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from nba.pinnacle_historical_probe import run


def payload():
    return {
        "data":[{
            "id":"e",
            "home_team":"Boston Celtics",
            "away_team":"New York Knicks",
            "commence_time":"2026-04-10T23:00:00Z",
            "bookmakers":[{
                "key":"pinnacle",
                "last_update":"2026-04-10T21:59:00Z",
                "markets":[
                    {"key":"h2h","outcomes":[
                        {"name":"Boston Celtics","price":1.9},
                        {"name":"New York Knicks","price":2.0}]},
                    {"key":"spreads","outcomes":[
                        {"name":"Boston Celtics","price":1.9,"point":-2.5},
                        {"name":"New York Knicks","price":1.9,"point":2.5}]},
                    {"key":"totals","outcomes":[
                        {"name":"Over","price":1.9,"point":220.5},
                        {"name":"Under","price":1.9,"point":220.5}]},
                ],
            }],
        }],
        "timestamp":"2026-04-10T22:00:00Z",
        "previous_timestamp":"2026-04-10T21:55:00Z",
        "next_timestamp":"2026-04-10T22:05:00Z",
        "usage":{"remaining":100},
    }


class PinnacleHistoricalProbeTests(unittest.TestCase):
    def test_historical_complete_snapshot_is_ready_diagnostic_only(self):
        with tempfile.TemporaryDirectory() as d, patch(
            "nba.pinnacle_historical_probe.fetch_historical_nba_odds_diagnostic",
            return_value=payload(),
        ), patch("nba.pinnacle_historical_probe.datetime") as clock:
            clock.now.return_value=datetime(2026,9,28,tzinfo=timezone.utc)
            clock.fromisoformat.side_effect=datetime.fromisoformat
            result=run(
                date_iso="2026-04-10T22:00:00Z",
                budget_path=str(Path(d)/"budget.json"),
            )
        self.assertEqual(result["state"],"HISTORICAL_PINNACLE_READY")
        self.assertEqual(result["complete_pinnacle_events"],1)
        self.assertFalse(result["production_market_authorized"])
        self.assertFalse(result["betting_certified"])

    def test_future_snapshot_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"past"):
            run(date_iso="2099-01-01T00:00:00Z")


if __name__=="__main__":
    unittest.main()
