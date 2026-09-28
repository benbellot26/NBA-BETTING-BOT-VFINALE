import unittest

from nba.acquisition import _historical_timestamp


class HistoricalTimestampTests(unittest.TestCase):
    def test_normalizes_utc_offset_to_z(self):
        self.assertEqual(
            _historical_timestamp("2026-03-20T20:00:00+00:00"),
            "2026-03-20T20:00:00Z",
        )

    def test_normalizes_non_utc_offset(self):
        self.assertEqual(
            _historical_timestamp("2026-03-20T21:00:00+01:00"),
            "2026-03-20T20:00:00Z",
        )

    def test_rejects_naive_timestamp(self):
        with self.assertRaisesRegex(ValueError,"timezone"):
            _historical_timestamp("2026-03-20T20:00:00")


if __name__=="__main__":
    unittest.main()
