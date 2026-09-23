import unittest
from unittest.mock import patch

from nba.odds_smoke import check_auth


class OddsSmokeTests(unittest.TestCase):
    def test_auth_success_never_returns_key(self):
        with patch("nba.odds_smoke.get_json", return_value=[{"key": "basketball_nba"}]) as mock:
            result = check_auth(api_key="PRIVATE-CANARY")
        self.assertTrue(result["authorized"])
        self.assertNotIn("PRIVATE-CANARY", repr(result))
        self.assertIn("PRIVATE-CANARY", mock.call_args.args[0])

    def test_missing_key_does_not_call_network(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "missing"):
                check_auth()


if __name__ == "__main__":
    unittest.main()
