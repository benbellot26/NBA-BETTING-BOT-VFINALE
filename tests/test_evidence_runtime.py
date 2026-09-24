import tempfile,unittest
from pathlib import Path
from nba.close_runtime import _close_row
from nba.performance_runtime import _read
from nba.prospective import record_paper_candidates

class EvidenceTests(unittest.TestCase):
    def test_paper_recording_uncertified_research_ready(self):
        run={"games":[{"phase":"FINAL","game_id":"g","odds_event_id":"odds-g","game_date":"2026-10-20","commence_time":"2026-10-20T23:00:00Z","home":"Boston Celtics","away":"New York Knicks","analyzed_at":"2026-10-20T22:45:00Z","decision":{"candidates":[{"paper_eligible":True,"status":"NO_BET","game_id":"g","market":"ML","selection":"home_ml","price":2.0,"line":None,"model_probability":.60,"lower_probability":.55,"sharp_probability":.52,"execution_book":"x","robust_edge_pp":5}]}}]}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"paper.jsonl";r=record_paper_candidates(run,p);self.assertEqual(r["added"],1);self.assertEqual(len(_read(p)),1);self.assertGreaterEqual(_read(p)[0]["stake_fraction"],0);self.assertEqual(_read(p)[0]["odds_event_id"],"odds-g")
    def test_close_row(self):
        entry={"entry_key":"x","game_id":"g","odds_event_id":"odds-g","market":"SPREAD","selection":"home_spread","line":-3.5,"price":1.95}
        event={"event_id":"odds-g","markets":{"SPREAD":[{"bookmaker":"pinnacle","selections":[{"selection":"HOME","price":1.9,"point":-5.0},{"selection":"AWAY","price":2.0,"point":5.0}]}]}}
        row=_close_row(entry,event,"x","live");self.assertAlmostEqual(row["line_clv"],1.5);self.assertFalse(row["price_clv_comparable"]);self.assertEqual(row["odds_event_id"],"odds-g")
if __name__=="__main__":unittest.main()
