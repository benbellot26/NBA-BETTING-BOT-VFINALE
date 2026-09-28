import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nba.historical_pinnacle_probe import run


def payload():
    return {
        "timestamp":"2026-03-20T22:25:00+00:00",
        "usage":{"remaining":100,"used":1,"last_cost":1},
        "data":[{
            "id":"x",
            "home_team":"Detroit Pistons",
            "away_team":"Golden State Warriors",
            "commence_time":"2026-03-20T23:00:00Z",
            "bookmakers":[{
                "key":"pinnacle",
                "last_update":"2026-03-20T22:29:00Z",
                "markets":[
                    {"key":"h2h","outcomes":[
                        {"name":"Detroit Pistons","price":1.9},
                        {"name":"Golden State Warriors","price":2.0}]},
                    {"key":"spreads","outcomes":[
                        {"name":"Detroit Pistons","price":1.91,"point":-2.5},
                        {"name":"Golden State Warriors","price":1.91,"point":2.5}]},
                    {"key":"totals","outcomes":[
                        {"name":"Over","price":1.91,"point":221.5},
                        {"name":"Under","price":1.91,"point":221.5}]},
                ],
            }],
        }],
    }


class HistoricalPinnacleProbeTests(unittest.TestCase):
    def test_ready_historical_pinnacle_probe(self):
        with tempfile.TemporaryDirectory() as d, patch(
            "nba.historical_pinnacle_probe.fetch_historical_nba_odds",
            return_value=payload(),
        ):
            result=run(
                output=str(Path(d)/"probe.json"),
                budget_path=str(Path(d)/"budget.json"),
            )
        self.assertEqual(result["state"],"PINNACLE_HISTORICAL_READY")
        self.assertTrue(result["historical_pinnacle_available"])
        self.assertTrue(all(result["paired_pinnacle_markets"].values()))
        self.assertFalse(result["used_for_certification"])
        self.assertFalse(result["betting_certified"])

    def test_absent_historical_pinnacle_is_explicit(self):
        value=payload()
        value["data"][0]["bookmakers"]=[]
        with tempfile.TemporaryDirectory() as d, patch(
            "nba.historical_pinnacle_probe.fetch_historical_nba_odds",
            return_value=value,
        ):
            result=run(
                output=str(Path(d)/"probe.json"),
                budget_path=str(Path(d)/"budget.json"),
            )
        self.assertEqual(result["state"],"PINNACLE_HISTORICAL_ABSENT")
        self.assertFalse(result["historical_pinnacle_available"])


if __name__=="__main__":
    unittest.main()
