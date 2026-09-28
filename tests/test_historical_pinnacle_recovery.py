import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nba.historical_pinnacle_recovery import recover


def forecast():
    return {
        "entry_key":"g1|pulsar-nba-v1-structural|FINAL",
        "role":"PIT_FINAL_FORECAST",
        "game_id":"g1",
        "game_date":"2026-10-20",
        "home":"Boston Celtics",
        "away":"New York Knicks",
        "forecast_at":"2026-10-20T20:00:00+00:00",
        "tipoff_at":"2026-10-20T22:00:00+00:00",
        "probabilities":{
            "home_ml":0.6,"away_ml":0.4,
            "home_spread":0.55,"away_spread":0.45,
            "over":0.52,"under":0.48,
            "spread_line":-2.5,"total_line":220.5,
        },
    }


def historical_payload():
    return {
        "timestamp":"2026-10-20T19:55:00+00:00",
        "data":[{
            "id":"e1","home_team":"Boston Celtics","away_team":"New York Knicks",
            "commence_time":"2026-10-20T22:00:00Z",
            "bookmakers":[{
                "key":"pinnacle","last_update":"2026-10-20T19:59:00Z",
                "markets":[
                    {"key":"h2h","last_update":"2026-10-20T19:59:00Z","outcomes":[
                        {"name":"Boston Celtics","price":1.8},
                        {"name":"New York Knicks","price":2.1}]},
                    {"key":"spreads","last_update":"2026-10-20T19:59:00Z","outcomes":[
                        {"name":"Boston Celtics","price":1.91,"point":-2.5},
                        {"name":"New York Knicks","price":1.91,"point":2.5}]},
                    {"key":"totals","last_update":"2026-10-20T19:59:00Z","outcomes":[
                        {"name":"Over","price":1.91,"point":220.5},
                        {"name":"Under","price":1.91,"point":220.5}]},
                ],
            }],
        }],
    }


class HistoricalPinnacleRecoveryTests(unittest.TestCase):
    def test_recovers_paired_entry_benchmark_without_mutating_forecast(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            forecasts=root/"forecasts.jsonl"
            output=root/"recovered.jsonl"
            budget=root/"budget.json"
            forecasts.write_text(json.dumps(forecast())+"\n",encoding="utf-8")
            with patch(
                "nba.historical_pinnacle_recovery.fetch_historical_nba_odds",
                return_value=historical_payload(),
            ):
                result=recover(
                    forecasts_path=str(forecasts),
                    output_path=str(output),
                    budget_path=str(budget),
                    max_snapshots=1,
                )
            self.assertEqual(result["added"],1)
            self.assertEqual(result["odds_api_requests"],1)
            row=json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(row["role"],"HISTORICAL_EVALUATION_ONLY")
            self.assertEqual(set(row["pinnacle_entry_probability"]),{"ML","SPREAD","TOTAL"})
            self.assertFalse(row["used_for_certification"])
            self.assertFalse(row["market_data_used_as_model_feature"])
            self.assertEqual(len(forecasts.read_text().splitlines()),1)

    def test_rejects_snapshot_after_forecast(self):
        payload=historical_payload()
        payload["timestamp"]="2026-10-20T20:01:00+00:00"
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            fp=root/"forecasts.jsonl"
            fp.write_text(json.dumps(forecast())+"\n",encoding="utf-8")
            with patch(
                "nba.historical_pinnacle_recovery.fetch_historical_nba_odds",
                return_value=payload,
            ):
                result=recover(
                    forecasts_path=str(fp),
                    output_path=str(root/"out.jsonl"),
                    budget_path=str(root/"budget.json"),
                    max_snapshots=1,
                )
            self.assertEqual(result["added"],0)
            self.assertTrue(result["failures"])


if __name__=="__main__":
    unittest.main()
