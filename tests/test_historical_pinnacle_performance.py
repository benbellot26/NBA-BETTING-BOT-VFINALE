import json
import tempfile
import unittest
from pathlib import Path

from nba.historical_pinnacle_performance import evaluate


class HistoricalPinnaclePerformanceTests(unittest.TestCase):
    def test_scores_model_and_recovered_pinnacle_on_same_contracts(self):
        forecast={
            "entry_key":"g1|v1|FINAL","game_id":"g1",
            "probabilities":{
                "home_ml":0.6,"away_ml":0.4,
                "home_spread":0.55,"away_spread":0.45,
                "over":0.52,"under":0.48,
                "spread_line":-2.5,"total_line":220.5,
            },
        }
        recovery={
            "schema":"pulsar-nba-historical-pinnacle-entry-v1",
            "role":"HISTORICAL_EVALUATION_ONLY",
            "entry_key":"g1|v1|FINAL|HIST_PIN",
            "forecast_entry_key":"g1|v1|FINAL",
            "game_id":"g1",
            "snapshot_age_minutes":5.0,
            "pinnacle_entry_probability":{"ML":0.58,"SPREAD":0.53,"TOTAL":0.51},
            "market_data_used_as_model_feature":False,
            "used_for_certification":False,
        }
        outcome={"game_id":"g1","home_score":112,"away_score":105}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            fp=root/"f.jsonl";op=root/"o.jsonl";rp=root/"r.jsonl";out=root/"p.json"
            fp.write_text(json.dumps(forecast)+"\n",encoding="utf-8")
            op.write_text(json.dumps(outcome)+"\n",encoding="utf-8")
            rp.write_text(json.dumps(recovery)+"\n",encoding="utf-8")
            result=evaluate(
                forecasts_path=str(fp),outcomes_path=str(op),
                recovery_path=str(rp),output_path=str(out))
            self.assertEqual(result["markets"]["ML"]["n"],1)
            self.assertIsNotNone(result["markets"]["ML"]["pinnacle_brier"])
            self.assertIsNotNone(result["markets"]["ML"]["model_brier_paired"])
            self.assertFalse(result["used_for_certification"])
            self.assertFalse(result["betting_certified"])


if __name__=="__main__":
    unittest.main()
