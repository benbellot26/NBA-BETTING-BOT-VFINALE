import unittest

from nba.model import GameContext, TeamMetrics
from nba.pipeline import analyze_game


class PipelineTests(unittest.TestCase):
    def test_research_payload_without_market(self):
        out=analyze_game(
            home=TeamMetrics("BOS",120,111,99),
            away=TeamMetrics("NYK",117,113,98),
            context=GameContext("1","2026-10-20","2026-10-20T20:00:00Z","BOS","NYK"),
            spread_line=-3.5,total_line=228.5,
        )
        self.assertFalse(out["market_probability_used_as_feature"])
        self.assertEqual(out["role"],"RESEARCH")
        self.assertIn("probability_intervals",out)

    def test_market_candidate_generated(self):
        books={"ML":[{"bookmaker":"pinnacle","selections":[{"selection":"HOME","price":2.00},{"selection":"AWAY","price":1.90}]}]}
        out=analyze_game(
            home=TeamMetrics("BOS",120,111,99),away=TeamMetrics("NYK",117,113,98),
            context=GameContext("1","2026-10-20","x","BOS","NYK"),spread_line=-3.5,total_line=228.5,books_by_market=books,
        )
        self.assertTrue(any(c["market"]=="ML" for c in out["decision"]["candidates"]))

if __name__ == "__main__": unittest.main()
