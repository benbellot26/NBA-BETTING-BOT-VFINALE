import unittest

from nba.gamebook_shadow_gate import assess


def report():
    return {
        "schema": "pulsar-nba-gamebook-provider-shadow-performance-v1",
        "role": "MANUAL_REVIEW_ONLY",
        "resolved_n": 300,
        "paired_v1_n": 150,
        "minimum_gamebook_completeness": 1.0,
        "paired_shadow_margin_mae": 10.0,
        "paired_v1_margin_mae": 10.05,
        "paired_shadow_total_mae": 12.0,
        "paired_v1_total_mae": 12.1,
        "paired_shadow_ml_brier": 0.245,
        "paired_v1_ml_brier": 0.247,
        "production_provider_authorized": False,
        "predictive_authority": False,
        "betting_certified": False,
        "review_ready": False,
    }


class GamebookShadowGateTests(unittest.TestCase):
    def test_good_evidence_only_becomes_manual_review_ready(self):
        result = assess(report())
        self.assertTrue(result["review_ready"])
        self.assertFalse(result["production_provider_authorized"])
        self.assertFalse(result["predictive_authority"])
        self.assertFalse(result["auto_promote"])
        self.assertFalse(result["betting_certified"])

    def test_small_sample_stays_shadow(self):
        value = report()
        value["resolved_n"] = 40
        value["paired_v1_n"] = 20
        result = assess(value)
        self.assertFalse(result["review_ready"])
        self.assertTrue(any(x.startswith("resolved_n<") for x in result["failures"]))

    def test_material_regression_blocks_review(self):
        value = report()
        value["paired_shadow_margin_mae"] = 10.5
        value["paired_v1_margin_mae"] = 10.0
        result = assess(value)
        self.assertFalse(result["review_ready"])
        self.assertIn("margin_mae_degradation>0.15", result["failures"])

    def test_forbidden_authority_state_is_rejected(self):
        value = report()
        value["production_provider_authorized"] = True
        with self.assertRaisesRegex(ValueError, "forbidden"):
            assess(value)


if __name__ == "__main__":
    unittest.main()
