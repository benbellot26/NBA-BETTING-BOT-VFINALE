import json
import tempfile
import unittest
from pathlib import Path

from nba.communications_schedule import ReferenceScheduleGame
from nba.gamebook import parse_final_box_text
from nba.gamebook_shadow_performance import evaluate
from nba.gamebook_stats import _json_sha256
from test_gamebook import FINAL_BOX


class GamebookProviderShadowPerformanceTests(unittest.TestCase):
    def test_scores_shadow_and_paired_v1_without_promotion(self):
        ref = ReferenceScheduleGame(
            reference_id="nba-pr-2025-26-2026-03-20-1",
            schedule_number=1,
            game_date="2026-03-20",
            commence_time="2026-03-20T23:00:00+00:00",
            team1="Golden State Warriors",
            team2="Detroit Pistons",
            relation="at",
            away="Golden State Warriors",
            home="Detroit Pistons",
            neutral_site=False,
        )
        parsed = parse_final_box_text(
            FINAL_BOX,
            expected_away="Golden State Warriors",
            expected_home="Detroit Pistons",
        )
        cache = {
            "schema": "pulsar-nba-gamebook-cache-v1",
            "source": "NBA_OFFICIAL_SCORERS_REPORT",
            "role": "ALTERNATE_REFERENCE_ONLY",
            "reference_id": ref.reference_id,
            "game_date": ref.game_date,
            "away": ref.away,
            "home": ref.home,
            "pdf_sha256": "a" * 64,
            "parsed_sha256": _json_sha256(parsed),
            "parsed": parsed,
        }
        shadow = {
            "schema": "pulsar-nba-gamebook-provider-shadow-forecast-v1",
            "role": "ALTERNATE_PROVIDER_SHADOW",
            "generation": "pulsar-nba-gamebook-provider-shadow-v1",
            "entry_key": f"{ref.reference_id}|pulsar-nba-gamebook-provider-shadow-v1|FINAL",
            "game_id": ref.reference_id,
            "game_date": ref.game_date,
            "home": ref.home,
            "away": ref.away,
            "forecast_at": "2026-03-20T22:40:00+00:00",
            "tipoff_at": ref.commence_time,
            "score_projection": {
                "margin_mean": 3.0,
                "total_mean": 222.0,
            },
            "home_ml": 0.60,
            "production_provider_authorized": False,
            "predictive_authority": False,
            "market_data_used": False,
            "betting_certified": False,
        }
        v1 = {
            "role": "PIT_FINAL_FORECAST",
            "game_date": ref.game_date,
            "home": ref.home,
            "away": ref.away,
            "baseline_margin": 1.0,
            "baseline_total": 219.0,
            "probabilities": {"home_ml": 0.55},
        }
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "gamebooks").mkdir()
            (root / "gamebooks" / f"{ref.reference_id}.json").write_text(
                json.dumps(cache), encoding="utf-8"
            )
            shadow_path = root / "shadow.jsonl"
            v1_path = root / "v1.jsonl"
            out = root / "performance.json"
            shadow_path.write_text(json.dumps(shadow) + "\n", encoding="utf-8")
            v1_path.write_text(json.dumps(v1) + "\n", encoding="utf-8")

            report = evaluate(
                forecasts_path=str(shadow_path),
                canonical_forecasts_path=str(v1_path),
                cache_root=str(root),
                output=str(out),
                reference_schedule=[ref],
            )
            self.assertEqual(report["resolved_n"], 1)
            self.assertEqual(report["paired_v1_n"], 1)
            self.assertIsNotNone(report["margin_mae"])
            self.assertIsNotNone(report["paired_v1_margin_mae"])
            self.assertFalse(report["production_provider_authorized"])
            self.assertFalse(report["predictive_authority"])
            self.assertFalse(report["betting_certified"])
            self.assertFalse(report["review_ready"])


if __name__ == "__main__":
    unittest.main()
