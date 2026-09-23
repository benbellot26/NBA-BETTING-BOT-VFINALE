import datetime as dt
import unittest

from nba import MODEL_GENERATION
from nba.v2_shadow import evaluate, validate_row


def _row(index: int) -> dict:
    tip = dt.datetime(2025, 10, 1, 23, tzinfo=dt.timezone.utc) + dt.timedelta(days=index)
    return {
        "game_id": f"g{index}", "model_generation": MODEL_GENERATION,
        "source_snapshot_sha256": "a" * 64,
        "source_snapshot_at": (tip - dt.timedelta(days=1)).isoformat(),
        "forecast_at": (tip - dt.timedelta(minutes=20)).isoformat(),
        "tipoff_at": tip.isoformat(),
        "outcome_at": (tip + dt.timedelta(hours=3)).isoformat(),
        "baseline_margin": 3 + index % 5 - 2,
        "baseline_total": 228 + index % 6,
        "baseline_margin_sd": 11.5, "baseline_total_sd": 17.0,
        "home_score": 115 + index % 6, "away_score": 112 + index % 5,
    }


class V2ShadowTests(unittest.TestCase):
    def test_pit_future_snapshot_rejected(self):
        row = _row(0)
        row["source_snapshot_at"] = row["outcome_at"]
        with self.assertRaisesRegex(ValueError, "look-ahead"):
            validate_row(row)

    def test_market_feature_rejected(self):
        row = _row(0)
        row["odds_feature"] = 1.95
        with self.assertRaisesRegex(ValueError, "market data"):
            validate_row(row)

    def test_training_label_cannot_arrive_after_cutoff(self):
        rows = [_row(i) for i in range(18)]
        with self.assertRaises(ValueError):
            evaluate(rows, train_cutoff=rows[1]["forecast_at"],
                     holdout_start=rows[11]["forecast_at"],
                     minimum_train=4, minimum_holdout=3)

    def test_shadow_evaluates_only_later_holdout(self):
        rows = [_row(i) for i in range(20)]
        cutoff = rows[10]["outcome_at"]
        start = rows[11]["forecast_at"]
        report = evaluate(rows, train_cutoff=cutoff, holdout_start=start,
                          minimum_train=10, minimum_holdout=5)
        self.assertEqual(report["role"], "SHADOW")
        self.assertFalse(report["promoted"])
        self.assertEqual(report["model"]["train_n"], 11)
        self.assertEqual(report["holdout_shadow"]["n"], 9)
        self.assertIn("ml_brier", report["holdout_champion"])
        self.assertIn("ml_brier", report["holdout_shadow"])


if __name__ == "__main__":
    unittest.main()
