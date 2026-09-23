import unittest

from nba.e2e_dryrun import run
from nba.fixture_provider import DeterministicFixtureProvider
from nba.provider_contract import ProviderSnapshot


class ProviderContractTests(unittest.TestCase):
    def test_fixture_snapshot_is_deterministic_and_pit(self):
        provider = DeterministicFixtureProvider()
        first = provider.capture(target_date="2026-11-15")
        second = provider.capture(target_date="2026-11-15")
        self.assertEqual(first.fingerprint(), second.fingerprint())
        self.assertEqual(first.role, "SYNTHETIC_CI_ONLY")

    def test_snapshot_future_stats_rejected(self):
        valid = DeterministicFixtureProvider().capture(target_date="2026-11-15")
        bad_stats = dict(valid.stats)
        bad_stats["observed_at"] = "2026-11-15T22:30:00Z"
        broken = ProviderSnapshot(
            target_date=valid.target_date, season=valid.season,
            captured_at=valid.captured_at, provider_id=valid.provider_id,
            schedule=valid.schedule, stats=bad_stats,
            injuries=valid.injuries, role=valid.role,
        )
        with self.assertRaisesRegex(ValueError, "stats observed after"):
            broken.validated()

    def test_e2e_never_authorizes_uncertified_bet(self):
        result = run()
        self.assertEqual(result["bet_count"], 0)
        self.assertGreaterEqual(result["candidate_count"], 6)
        self.assertTrue(result["all_probabilities_valid"])
        self.assertTrue(result["rotations_240"])


if __name__ == "__main__":
    unittest.main()
