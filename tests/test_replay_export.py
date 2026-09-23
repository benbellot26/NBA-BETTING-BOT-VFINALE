import tempfile
import unittest
from pathlib import Path

from nba import MODEL_GENERATION
from nba.prospective import record_final_forecasts
from nba.replay_export import join, export


def sample():
    return {
        "game_id": "g", "game_date": "2026-10-21", "model_generation": MODEL_GENERATION,
        "phase": "FINAL", "analyzed_at": "2026-10-21T22:40:00Z",
        "commence_time": "2026-10-21T23:00:00Z",
        "source_snapshot_at": "2026-10-21T20:00:00Z",
        "source_snapshot_sha256": "a" * 64,
        "input_quality": {"eligible": True},
        "score_projection": {"margin_mean": 3.0, "total_mean": 225.0,
                             "margin_sd": 11.5, "total_sd": 17.0},
    }


class ReplayExportTests(unittest.TestCase):
    def test_final_snapshot_is_append_only_and_unselected(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "final.jsonl"
            self.assertEqual(record_final_forecasts({"games": [sample()]}, target)["added"], 1)
            self.assertEqual(record_final_forecasts({"games": [sample()]}, target)["added"], 0)
            self.assertEqual(len(target.read_text().splitlines()), 1)

    def test_outcomes_must_be_official_and_observed_after_tip(self):
        forecast = {
            "game_id": "g", "model_generation": MODEL_GENERATION,
            "source_snapshot_sha256": "a" * 64,
            "source_snapshot_at": "2026-10-21T20:00:00Z",
            "forecast_at": "2026-10-21T22:40:00Z",
            "tipoff_at": "2026-10-21T23:00:00Z",
            "baseline_margin": 3.0, "baseline_total": 225.0,
            "baseline_margin_sd": 11.5, "baseline_total_sd": 17.0,
        }
        with self.assertRaisesRegex(ValueError, "unverified"):
            join([forecast], [{"game_id": "g", "source": "unknown",
                               "outcome_at": "2026-10-22T03:00:00Z",
                               "home_score": 116, "away_score": 111}])
        rows = join([forecast], [{"game_id": "g", "source": "official_nba_schedule",
                                  "outcome_at": "2026-10-22T03:00:00Z",
                                  "home_score": 116, "away_score": 111}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["home_score"], 116.0)

    def test_empty_export_is_forbidden(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError, "no settled"):
                export(forecasts_path=str(Path(d) / "missing"),
                       outcomes_path=str(Path(d) / "missing"),
                       output=str(Path(d) / "out.jsonl"))


if __name__ == "__main__":
    unittest.main()
