import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nba import MODEL_GENERATION
from nba.certification import certify
from nba.distribution import probability_surface
from nba.lineage import build_input_manifest
from nba.model import GameContext, ScoreProjection, TeamMetrics
from nba.performance_runtime import refresh
from nba.rotations import RotationPlayer
from nba.schedule import ScheduleGame
from nba.tracking import append_jsonl


def fixture():
    at = "2026-08-01T21:40:00Z"
    tip = "2026-08-01T22:00:00Z"
    context = GameContext(
        "synthetic-g", "2026-08-01", at, "H", "A", phase="FINAL")
    home, away = TeamMetrics("H", 118, 112, 99), TeamMetrics("A", 114, 115, 99)
    manifest = build_input_manifest(
        context=context, home=home, away=away,
        home_rotation=[RotationPlayer("h", "H", 240)],
        away_rotation=[RotationPlayer("a", "A", 240)],
        stats_snapshot_sha256="a" * 64,
        stats_observed_at="2026-08-01T18:00:00Z",
        injury_snapshot_sha256="b" * 64,
        injury_reported_at="2026-08-01T21:30:00Z",
    )
    projection = ScoreProjection(
        "synthetic-g", "2026-08-01", at, "H", "A",
        114, 109, 99, 5, 223)
    from dataclasses import asdict
    probability = asdict(probability_surface(
        projection, spread_line=-3.5, total_line=225.5))
    forecast = {
        "entry_key": "synthetic-g|" + MODEL_GENERATION + "|FINAL",
        "game_id": "synthetic-g", "role": "PIT_FINAL_FORECAST",
        "model_generation": MODEL_GENERATION,
        "source_snapshot_sha256": manifest["sha256"],
        "source_snapshot_at": manifest["source_snapshot_at"],
        "forecast_at": at, "tipoff_at": tip,
        "input_manifest": manifest, "probabilities": probability,
        "baseline_margin": 5, "baseline_total": 223,
        "baseline_margin_sd": 11.5, "baseline_total_sd": 17.0,
    }
    paper = {
        "entry_key": "synthetic-g|ML|home_ml", "game_id": "synthetic-g",
        "market": "ML", "selection": "home_ml", "status": "PAPER",
        "phase": "FINAL", "model_generation": MODEL_GENERATION,
        "source_snapshot_sha256": manifest["sha256"],
        "source_snapshot_at": manifest["source_snapshot_at"],
        "input_manifest": manifest, "entry_at": at, "commence_time": tip,
        "price": 2.0, "stake_fraction": .01, "line": None,
        "model_probability": probability["home_ml"],
    }
    game = ScheduleGame(
        "synthetic-g", "2026-08-01", tip, "H", "A",
        3, "Final", 116, 111,
    )
    return forecast, paper, game


def arguments(directory):
    root = Path(directory)
    return {
        "paper_path": str(root / "paper.jsonl"),
        "close_path": str(root / "close.jsonl"),
        "settled_path": str(root / "settled.jsonl"),
        "forecasts_path": str(root / "forecasts.jsonl"),
        "outcomes_path": str(root / "outcomes.jsonl"),
        "performance_path": str(root / "performance.json"),
        "certification_path": str(root / "candidate.json"),
        "audit_path": str(root / "audit.json"),
    }


class FullCohortTests(unittest.TestCase):
    def test_empty_selected_cohort_does_not_hide_full_game_metrics(self):
        forecast, _, game = fixture()
        with tempfile.TemporaryDirectory() as directory:
            args = arguments(directory)
            append_jsonl(args["forecasts_path"], forecast)
            with patch("nba.performance_runtime.fetch_schedule", return_value=[game]):
                result = refresh(**args)
            self.assertTrue(result["evidence"]["audit_ok"],
                            result["evidence"]["audit_errors"])
            self.assertEqual(result["evidence"]["games"], 1)
            for market in ("ML", "SPREAD", "TOTAL"):
                self.assertEqual(result["evidence"]["markets"][market]["full_cohort_n"], 1)
                self.assertEqual(result["evidence"]["markets"][market]["n"], 0)
            self.assertFalse(result["certified"])
            self.assertFalse(result["approved_for_live"])

    def test_late_close_updates_derived_metrics_not_original_settlement(self):
        forecast, paper, game = fixture()
        with tempfile.TemporaryDirectory() as directory:
            args = arguments(directory)
            append_jsonl(args["forecasts_path"], forecast)
            append_jsonl(args["paper_path"], paper)
            with patch("nba.performance_runtime.fetch_schedule", return_value=[game]):
                first = refresh(**args)
            self.assertTrue(first["evidence"]["audit_ok"])
            self.assertEqual(first["evidence"]["markets"]["ML"]["clv_n"], 0)
            close = {
                "entry_key": paper["entry_key"],
                "game_id": "synthetic-g",
                "market": "ML", "selection": "home_ml",
                "captured_at": "2026-08-01T21:59:00Z",
                "pinnacle_close_no_vig_probability": .53,
                "price_clv_comparable": True, "clv_pp": 3.0,
            }
            append_jsonl(args["close_path"], close)
            with patch("nba.performance_runtime.fetch_schedule", return_value=[game]):
                second = refresh(**args)
            self.assertTrue(second["evidence"]["audit_ok"],
                            second["evidence"]["audit_errors"])
            self.assertEqual(second["evidence"]["markets"]["ML"]["clv_n"], 1)
            self.assertAlmostEqual(
                second["evidence"]["markets"]["ML"]["mean_clv_pp"], 3.0)
            original = Path(args["settled_path"]).read_text().splitlines()
            self.assertEqual(len(original), 1)
            self.assertNotIn("clv_pp", json.loads(original[0]))

    def test_candidate_rejects_missing_clv_rate_and_accepts_zero_ece(self):
        market = {
            "n": 400, "ece": 0.0, "full_cohort_n": 400,
            "full_cohort_ece": 0.0, "paired_sharp_n": 400,
            "clv_n": 100, "positive_clv_rate": .55,
        }
        evidence = {
            "audit_ok": True, "games": 600,
            "markets": {key: dict(market) for key in ("ML", "SPREAD", "TOTAL")},
        }
        passed = certify(evidence)
        self.assertTrue(passed["certified"], passed["failures"])
        self.assertFalse(passed["approved_for_live"])
        evidence["markets"]["ML"]["positive_clv_rate"] = None
        rejected = certify(evidence)
        self.assertFalse(rejected["certified"])
        self.assertTrue(any("positive_clv_rate" in x for x in rejected["failures"]))


if __name__ == "__main__":
    unittest.main()
