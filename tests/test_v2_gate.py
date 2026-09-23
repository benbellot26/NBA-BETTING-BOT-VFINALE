import unittest

from nba.v2_gate import assess


def report(n=300):
    champion = {
        "n": n, "ml_brier": .235, "ml_logloss": .665, "ml_ece": .045,
        "margin_mae": 9.1, "total_mae": 12.6,
    }
    shadow = {
        "n": n, "ml_brier": .230, "ml_logloss": .660, "ml_ece": .043,
        "margin_mae": 9.0, "total_mae": 12.55,
    }
    return {
        "role": "SHADOW", "promoted": False,
        "auto_betting_certification": False,
        "holdout_champion": champion, "holdout_shadow": shadow,
    }


class V2GateTests(unittest.TestCase):
    def test_good_shadow_only_becomes_manual_review_ready(self):
        result = assess(report())
        self.assertTrue(result["review_ready"])
        self.assertFalse(result["auto_promote"])
        self.assertFalse(result["betting_certified"])
        self.assertGreaterEqual(result["strict_improvements"], 2)

    def test_small_sample_stays_shadow(self):
        result = assess(report(100))
        self.assertFalse(result["review_ready"])
        self.assertIn("holdout_n<250", result["failures"])

    def test_one_material_regression_blocks_review(self):
        data = report()
        data["holdout_shadow"]["ml_brier"] = .25
        result = assess(data)
        self.assertFalse(result["review_ready"])
        self.assertTrue(any("ml_brier_degradation" in failure
                            for failure in result["failures"]))

    def test_mismatched_holdout_sizes_block_review(self):
        data = report()
        data["holdout_shadow"]["n"] = 299
        result = assess(data)
        self.assertIn("paired_holdout_size_mismatch", result["failures"])

    def test_forbidden_auto_promotion_state_is_rejected(self):
        data = report()
        data["promoted"] = True
        with self.assertRaisesRegex(ValueError, "forbidden"):
            assess(data)


if __name__ == "__main__":
    unittest.main()
