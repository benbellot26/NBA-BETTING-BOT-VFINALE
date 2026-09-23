import unittest
from unittest.mock import patch
from nba.market_smoke import run

class MarketSmokeTests(unittest.TestCase):
    def test_empty_market_is_diagnostic_not_certification(self):
        with patch("nba.market_smoke.fetch_nba_odds_diagnostic",
                   return_value={"events":[],"usage":{"remaining":99}}):
            result=run()
        self.assertFalse(result["coverage_ready"])
        self.assertFalse(result["betting_certified"])
        self.assertEqual(result["request_count"],1)
        self.assertEqual(result["quota"]["remaining"],99)
if __name__=="__main__":unittest.main()
