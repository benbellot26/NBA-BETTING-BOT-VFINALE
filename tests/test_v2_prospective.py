import datetime as dt
import json
import math
import tempfile
import unittest
from pathlib import Path

from nba.v2_prospective import evaluate
from nba.v2_runtime import run as shadow_run
from test_v2_model import row


class V2ProspectiveTests(unittest.TestCase):
    def _live_game(self, index: int) -> tuple[dict, dict]:
        source = row(index)
        margin = float(source["baseline_margin"])
        total = float(source["baseline_total"])
        game = {
            "game_id": source["game_id"],
            "home": "H",
            "away": "A",
            "phase": "FINAL",
            "analyzed_at": source["forecast_at"],
            "commence_time": source["tipoff_at"],
            "source_snapshot_sha256": source["source_snapshot_sha256"],
            "v2_features": source["v2_features"],
            "score_projection": {
                "margin_mean": margin,
                "total_mean": total,
                "margin_sd": 11.5,
                "total_sd": 17.0,
            },
            "probabilities": {
                "home_ml": 0.56,
                "home_spread": 0.52,
                "over": 0.51,
                "spread_line": -3.5,
                "total_line": 226.5,
            },
            "decision": {
                "candidates": [
                    {"selection": "home_ml", "sharp_probability": 0.53},
                    {"selection": "home_spread", "sharp_probability": 0.51},
                    {"selection": "over", "sharp_probability": 0.50},
                ]
            },
        }
        return source, game

    def test_future_shadow_forecast_and_official_scoring(self):
        training = [row(i) for i in range(100)]
        source, game = self._live_game(160)
        live = {"operating_mode": "regular", "games": [game]}
        tip = dt.datetime.fromisoformat(source["tipoff_at"])
        outcome = {
            "game_id": source["game_id"],
            "home_score": 120,
            "away_score": 110,
            "outcome_at": (tip + dt.timedelta(hours=3)).isoformat(),
            "source": "official_nba_schedule",
        }

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            live_path = root / "live.json"
            shadow_path = root / "shadow.jsonl"
            status_path = root / "status.json"
            outcomes_path = root / "outcomes.jsonl"
            report_path = root / "report.json"
            live_path.write_text(json.dumps(live), encoding="utf-8")
            outcomes_path.write_text(json.dumps(outcome) + "\n", encoding="utf-8")

            result = shadow_run(
                live_run_path=str(live_path),
                output_path=str(shadow_path),
                status_path=str(status_path),
                minimum_train=60,
                training_rows=training,
            )
            self.assertEqual(result["status"], "SHADOW_FORECASTS_RECORDED")
            self.assertEqual(result["added"], 1)
            forecast = json.loads(shadow_path.read_text(encoding="utf-8"))
            self.assertEqual(forecast["role"], "SHADOW_PIT_FORECAST")
            self.assertFalse(forecast["promoted"])
            self.assertFalse(forecast["betting_certified"])
            self.assertFalse(forecast["market_data_used_as_feature"])
            self.assertNotIn("stake_fraction", forecast)
            self.assertTrue(math.isfinite(forecast["prediction"]["margin_mean"]))

            report = evaluate(
                forecasts_path=str(shadow_path),
                outcomes_path=str(outcomes_path),
                output_path=str(report_path),
            )
            self.assertEqual(report["status"], "PROSPECTIVE_EVIDENCE")
            self.assertEqual(report["holdout_shadow"]["n"], 1)
            self.assertEqual(report["holdout_champion"]["n"], 1)
            self.assertEqual(report["holdout_pinnacle_entry"]["ml_n"], 1)
            self.assertFalse(report["promoted"])
            self.assertFalse(report["auto_betting_certification"])

    def test_official_gamebook_outcome_is_accepted(self):
        training = [row(i) for i in range(100)]
        source, game = self._live_game(160)
        live = {"operating_mode": "regular", "games": [game]}
        tip = dt.datetime.fromisoformat(source["tipoff_at"])
        outcome = {
            "game_id": source["game_id"],
            "home_score": 120,
            "away_score": 110,
            "outcome_at": (tip + dt.timedelta(hours=3)).isoformat(),
            "source": "official_nba_gamebook",
        }
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            live_path = root / "live.json"
            shadow_path = root / "shadow.jsonl"
            status_path = root / "status.json"
            outcomes_path = root / "outcomes.jsonl"
            report_path = root / "report.json"
            live_path.write_text(json.dumps(live), encoding="utf-8")
            outcomes_path.write_text(json.dumps(outcome) + "\n", encoding="utf-8")
            shadow_run(
                live_run_path=str(live_path),
                output_path=str(shadow_path),
                status_path=str(status_path),
                minimum_train=60,
                training_rows=training,
            )
            report = evaluate(
                forecasts_path=str(shadow_path),
                outcomes_path=str(outcomes_path),
                output_path=str(report_path),
            )
        self.assertEqual(report["status"], "PROSPECTIVE_EVIDENCE")
        self.assertEqual(report["holdout_shadow"]["n"], 1)

    def test_inference_does_not_need_outcome_label(self):
        training = [row(i) for i in range(100)]
        source, game = self._live_game(160)
        future = {
            "v2_features": source["v2_features"],
            "source_snapshot_sha256": source["source_snapshot_sha256"],
        }
        from nba.v2_model import fit_learned_v2
        model = fit_learned_v2(training, minimum_train=60)
        prediction = model.predict(future)
        self.assertIn("home_ml", prediction)


if __name__ == "__main__":
    unittest.main()
