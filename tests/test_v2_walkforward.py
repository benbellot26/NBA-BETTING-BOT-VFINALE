import unittest

from nba.v2_gate import assess
from nba.v2_walkforward import walk_forward
from test_v2_model import row


class V2WalkForwardTests(unittest.TestCase):
    def test_expanding_pit_evaluation_never_promotes(self):
        rows = [row(i) for i in range(150)]
        report = walk_forward(
            rows, minimum_train=80, minimum_holdout=50, step=20,
        )
        self.assertEqual(report["role"], "SHADOW")
        self.assertFalse(report["promoted"])
        self.assertFalse(report["auto_betting_certification"])
        self.assertFalse(report["market_data_used_as_feature"])
        self.assertGreaterEqual(report["holdout_shadow"]["n"], 50)
        self.assertIn("spread_brier", report["holdout_shadow"])
        self.assertGreater(report["holdout_pinnacle_entry"]["ml_n"], 0)
        for fold in report["folds"]:
            self.assertGreaterEqual(fold["train_n"], 80)

    def test_gate_accepts_richer_report_shape_without_auto_promotion(self):
        rows = [row(i) for i in range(150)]
        report = walk_forward(
            rows, minimum_train=80, minimum_holdout=50, step=20,
        )
        gate = assess(report, minimum_holdout=50)
        self.assertFalse(gate["auto_promote"])
        self.assertFalse(gate["betting_certified"])


if __name__ == "__main__":
    unittest.main()
