import unittest
from unittest.mock import patch

from nba.acquisition import (
    NBA_PRESEASON_SPORT_KEY,
    NBA_REGULAR_SPORT_KEY,
    fetch_nba_odds_diagnostic,
)


class OddsSportKeyTests(unittest.TestCase):
    def test_regular_and_preseason_use_distinct_provider_paths(self):
        calls=[]
        def fake(url, **kwargs):
            calls.append(url)
            return [], {}
        with patch("nba.acquisition.get_json_with_headers",side_effect=fake):
            fetch_nba_odds_diagnostic(api_key="x",sport_key=NBA_REGULAR_SPORT_KEY)
            fetch_nba_odds_diagnostic(api_key="x",sport_key=NBA_PRESEASON_SPORT_KEY)
        self.assertIn("/sports/basketball_nba/odds/",calls[0])
        self.assertIn("/sports/basketball_nba_preseason/odds/",calls[1])

    def test_unknown_sport_key_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"unsupported"):
            fetch_nba_odds_diagnostic(api_key="x",sport_key="basketball_fake")


if __name__=="__main__":
    unittest.main()
