import json
import tempfile
import unittest
from pathlib import Path

from nba.injury_pdf import game_report_ready
from nba.live_inputs import prior_day_cutoff
from nba.live_runtime import _load_cert, _unmatched_injuries
from nba.market import fresh_quote
from nba.model import GameContext, TeamMetrics
from nba.pipeline import analyze_game
from nba.rotations import RotationPlayer


class RuntimeGateTests(unittest.TestCase):
    def test_research_candidate_cannot_auto_certify_from_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            candidate = Path(folder) / "certification_candidate.json"
            candidate.write_text(json.dumps({"certified": True, "markets": {
                "ML": {"betting_certified": True}}}), encoding="utf-8")
            self.assertFalse(_load_cert(str(candidate))["certified"])

    def test_prev_day_stats_cutoff(self):
        self.assertEqual(prior_day_cutoff("2026-10-21"), "10/20/2026")

    def test_missing_team_submission_blocks_game(self):
        report = {"team_status": {
            "2026-10-21|Boston Celtics": "SUBMITTED",
            "2026-10-21|New York Knicks": "NOT_YET_SUBMITTED"}}
        self.assertFalse(game_report_ready(
            report, game_date="2026-10-21",
            home="Boston Celtics", away="New York Knicks"))

    def test_unmatched_key_injury_blocks_risk(self):
        report = {"records": [{"player_name": "Jayson Tatum", "status": "OUT",
                               "team": "Boston Celtics", "game_date": "2026-10-21",
                               "reason": "Injury/Illness"}]}
        roster = [RotationPlayer("1", "Jaylen Brown", 35)]
        self.assertEqual(_unmatched_injuries(report, "Boston Celtics", "2026-10-21", roster),
                         ["Jayson Tatum"])

    def test_no_paper_on_old_quotes(self):
        context = GameContext(
            "g", "2026-10-21", "2026-10-21T22:00:00Z", "Boston Celtics", "New York Knicks",
            phase="FINAL")
        books = {"ML": [{"bookmaker": "pinnacle", "last_update": "2026-10-21T21:00:00Z",
                         "selections": [{"selection": "HOME", "price": 2.00},
                                        {"selection": "AWAY", "price": 1.90}]}]}
        result = analyze_game(home=TeamMetrics("Boston Celtics", 120, 112, 99),
                              away=TeamMetrics("New York Knicks", 114, 115, 99),
                              context=context, spread_line=-3.5, total_line=229.5,
                              books_by_market=books, betting_window_ok=True)
        self.assertTrue(result["decision"]["candidates"])
        self.assertTrue(all(not c["paper_eligible"] for c in result["decision"]["candidates"]))

    def test_whole_number_totals_are_research_only(self):
        context = GameContext("g", "2026-10-21", "2026-10-21T22:00:00Z",
                              "Boston Celtics", "New York Knicks", phase="FINAL")
        books = {"TOTAL": [{"bookmaker": "pinnacle", "last_update": "2026-10-21T21:59:00Z",
                            "selections": [{"selection": "OVER", "point": 225.0, "price": 2.0},
                                           {"selection": "UNDER", "point": 225.0, "price": 1.9}]}]}
        result = analyze_game(home=TeamMetrics("Boston Celtics", 120, 112, 99),
                              away=TeamMetrics("New York Knicks", 114, 115, 99),
                              context=context, spread_line=-3.5, total_line=225.0,
                              books_by_market=books, betting_window_ok=True)
        self.assertTrue(all("whole_point_push_not_modeled" in c["failures"]
                            for c in result["decision"]["candidates"]))


if __name__ == "__main__":
    unittest.main()
