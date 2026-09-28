import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from nba.market_smoke import run

class MarketSmokeTests(unittest.TestCase):
    def test_empty_market_is_diagnostic_not_certification(self):
        with patch("nba.market_smoke.fetch_nba_odds_diagnostic",
                   return_value={"events":[],"usage":{"remaining":99}}):
            with tempfile.TemporaryDirectory() as folder:
                result=run(budget_path=str(Path(folder)/"budget.json"))
        self.assertFalse(result["coverage_ready"])
        self.assertFalse(result["betting_certified"])
        self.assertEqual(result["request_count"],1)
        self.assertEqual(result["quota"]["remaining"],99)
        self.assertEqual(result["availability_state"],"NO_NBA_EVENTS")
        self.assertFalse(result["pinnacle_replacement_allowed"])

    def test_events_without_pinnacle_are_classified_explicitly(self):
        raw={"id":"x","home_team":"Boston Celtics","away_team":"New York Knicks",
             "commence_time":"2026-10-20T22:00:00Z","bookmakers":[]}
        with patch("nba.market_smoke.fetch_nba_odds_diagnostic",
                   return_value={"events":[raw],"usage":{}}):
            with tempfile.TemporaryDirectory() as folder:
                result=run(budget_path=str(Path(folder)/"budget.json"))
        self.assertEqual(result["availability_state"],"PINNACLE_ABSENT")
        self.assertFalse(result["coverage_ready"])
if __name__=="__main__":unittest.main()
