import datetime as dt
import math
import unittest

from nba import MODEL_GENERATION
from nba.v2_dataset import feature_vector
from nba.v2_features import FEATURE_NAMES, FEATURE_SCHEMA
from nba.v2_model import fit_learned_v2


def row(index: int) -> dict:
    tip = dt.datetime(2026, 10, 1, 23, tzinfo=dt.timezone.utc) + dt.timedelta(days=index)
    baseline_margin = float((index % 13) - 6)
    baseline_total = 222.0 + float(index % 11)
    features = {name: 0.0 for name in FEATURE_NAMES}
    features.update({
        "baseline_margin": baseline_margin,
        "baseline_total": baseline_total,
        "baseline_possessions": 97.0 + index % 6,
        "baseline_margin_sd": 11.5,
        "baseline_total_sd": 17.0,
        "home_ortg": 112.0 + index % 9,
        "away_ortg": 111.0 + (index * 2) % 9,
        "home_drtg": 113.0 + index % 7,
        "away_drtg": 114.0 + (index * 3) % 7,
        "home_pace": 97.0 + index % 5,
        "away_pace": 98.0 + (index * 2) % 5,
    })
    actual_margin = 1.25 + 0.78 * baseline_margin + 0.08 * (features["home_ortg"] - features["away_drtg"])
    actual_total = 18.0 + 0.92 * baseline_total + 0.10 * (features["home_pace"] + features["away_pace"])
    home_score = (actual_total + actual_margin) / 2.0
    away_score = (actual_total - actual_margin) / 2.0
    return {
        "game_id": f"g{index}",
        "model_generation": MODEL_GENERATION,
        "source_snapshot_sha256": f"{index:064x}"[-64:],
        "source_snapshot_at": (tip - dt.timedelta(hours=2)).isoformat(),
        "forecast_at": (tip - dt.timedelta(minutes=20)).isoformat(),
        "tipoff_at": tip.isoformat(),
        "outcome_at": (tip + dt.timedelta(hours=3)).isoformat(),
        "baseline_margin": baseline_margin,
        "baseline_total": baseline_total,
        "baseline_margin_sd": 11.5,
        "baseline_total_sd": 17.0,
        "home_score": home_score,
        "away_score": away_score,
        "v2_features": {"schema": FEATURE_SCHEMA, "features": features},
        "evaluation_only": {
            "spread_line": -3.5,
            "total_line": 226.5,
            "pinnacle_entry_probability": {"ML": 0.5, "SPREAD": 0.5, "TOTAL": 0.5},
        },
    }


class V2ModelTests(unittest.TestCase):
    def test_market_metadata_never_changes_training_vector(self):
        a = row(1)
        b = row(1)
        b["evaluation_only"]["pinnacle_entry_probability"]["ML"] = 0.99
        b["evaluation_only"]["spread_line"] = 20.5
        self.assertEqual(feature_vector(a), feature_vector(b))

    def test_learned_model_fits_multifeature_signal(self):
        rows = [row(i) for i in range(100)]
        model = fit_learned_v2(rows, minimum_train=60)
        estimate = model.predict(row(101))
        self.assertTrue(math.isfinite(estimate["margin_mean"]))
        self.assertTrue(math.isfinite(estimate["total_mean"]))
        self.assertGreaterEqual(estimate["margin_sd"], 7.5)
        self.assertGreaterEqual(estimate["total_sd"], 10.0)
        self.assertEqual(model.role, "SHADOW")
        self.assertEqual(model.train_n, 100)


if __name__ == "__main__":
    unittest.main()
