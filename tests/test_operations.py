import tempfile, unittest
from pathlib import Path
from unittest.mock import patch

from nba.automation_window import representative_checks
from nba.health_report import build
from nba.preseason_rehearsal import run
from nba.provider_http import _default_headers
from nba.providers import OfficialOutcomeProvider
from nba.schedule import ScheduleGame

class OperationsTests(unittest.TestCase):
    def test_provider_headers_do_not_leak_nba_origin(self):
        odds=_default_headers("https://api.the-odds-api.com/v4/sports")
        nba=_default_headers("https://stats.nba.com/stats/leaguedashteamstats")
        self.assertNotIn("Origin", odds)
        self.assertEqual(nba["Origin"], "https://www.nba.com")

    def test_dst_window_covers_representative_nba_tips(self):
        self.assertTrue(all(representative_checks().values()))

    def test_rehearsal_is_never_evidence_or_betting(self):
        result=run()
        self.assertFalse(result["betting_certified"])
        self.assertFalse(result["prospective_evidence_eligible"])
        self.assertEqual(result["odds_api_requests"],0)
        self.assertEqual(result["fixture"]["bet_count"],0)

    def test_health_report_tolerates_empty_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            result=build(d)
        self.assertFalse(result["live_operational"])
        self.assertEqual(result["evidence"]["forecasts"],0)

    def test_outcomes_are_behind_provider_adapter(self):
        games=[ScheduleGame("g","2026-10-20","2026-10-20T23:00:00Z","Boston Celtics","New York Knicks",3,"Final",120,110)]
        with patch("nba.providers.fetch_schedule",return_value=games):
            finals=OfficialOutcomeProvider().finals()
        self.assertEqual(finals["g"].home_score,120)

if __name__=="__main__":unittest.main()
