import unittest

from nba.close_runtime import _failure_code


class CloseFailureCodeTests(unittest.TestCase):
    def test_structured_close_failure_codes(self):
        cases={
            "Pinnacle close missing":"PINNACLE_ABSENT",
            "Pinnacle close quote is stale or missing":"PINNACLE_STALE",
            "paired Pinnacle close at the same contract missing":"CONTRACT_MISSING",
            "event not found in close snapshot":"EVENT_NOT_FOUND",
            "live odds arrived at or after tip-off":"TIMING_INVALID",
            "live_odds:provider failed":"ODDS_PROVIDER_ERROR",
        }
        for message,expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(_failure_code(message),expected)


if __name__=="__main__":
    unittest.main()
