import unittest
from nba.health_gate import evaluate
from nba.close_runtime import _close_row

class AlertAndCloseTests(unittest.TestCase):
    def test_blocked_analysis_fails_health_gate(self):
        self.assertFalse(evaluate({"state":"ANALYSIS_BLOCKED"})["ok"])
        self.assertTrue(evaluate({"state":"READY_FOR_REHEARSAL"})["ok"])

    def test_close_prefers_exact_entry_contract(self):
        entry={"entry_key":"x","game_id":"g","market":"SPREAD","selection":"home_spread","line":-3.5,"price":1.95}
        event={"markets":{"SPREAD":[{"bookmaker":"pinnacle","selections":[
            {"selection":"HOME","price":1.88,"point":-5.0},{"selection":"AWAY","price":2.02,"point":5.0},
            {"selection":"HOME","price":1.91,"point":-3.5},{"selection":"AWAY","price":1.99,"point":3.5}
        ]}]}}
        row=_close_row(entry,event,"2026-11-15T22:19:00Z","test")
        self.assertEqual(row["close_line"],-3.5)
        self.assertTrue(row["price_clv_comparable"])
if __name__=="__main__":unittest.main()
