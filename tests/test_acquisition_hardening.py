import unittest
from unittest.mock import MagicMock, patch

from nba.live_inputs import _cache_is_fresh
from nba.provider_http import headers_for


class AcquisitionHardeningTests(unittest.TestCase):
    def test_nba_headers_only_sent_to_nba_domains(self):
        nba = headers_for("https://stats.nba.com/stats/leaguedashteamstats")
        odds = headers_for("https://api.the-odds-api.com/v4/sports")
        self.assertEqual(nba["Origin"], "https://www.nba.com")
        self.assertEqual(nba["Referer"], "https://www.nba.com/")
        self.assertNotIn("Origin", odds)
        self.assertNotIn("Referer", odds)

    def test_explicit_headers_override_provider_defaults(self):
        row = headers_for("https://stats.nba.com/x", {"Referer": "https://example.invalid/"})
        self.assertEqual(row["Referer"], "https://example.invalid/")

    def test_stats_cache_must_be_recent_and_same_pit_cutoff(self):
        payload = {
            "season": "2026-27", "date_to": "11/14/2026",
            "observed_at": "2026-11-15T10:00:00Z",
        }
        self.assertTrue(_cache_is_fresh(
            payload, observed_at="2026-11-15T20:00:00Z",
            season="2026-27", date_to="11/14/2026"))
        self.assertFalse(_cache_is_fresh(
            payload, observed_at="2026-11-15T23:00:01Z",
            season="2026-27", date_to="11/14/2026"))
        self.assertFalse(_cache_is_fresh(
            payload, observed_at="2026-11-15T20:00:00Z",
            season="2026-27", date_to="11/13/2026"))

    def test_future_cached_observation_is_not_reused(self):
        payload = {
            "season": "2026-27", "date_to": "11/14/2026",
            "observed_at": "2026-11-15T21:00:00Z",
        }
        self.assertFalse(_cache_is_fresh(
            payload, observed_at="2026-11-15T20:00:00Z",
            season="2026-27", date_to="11/14/2026"))


if __name__ == "__main__":
    unittest.main()
