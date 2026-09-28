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
        self.assertNotIn("x-nba-stats-token", odds)
        self.assertEqual(nba["Origin"], "https://www.nba.com")
        self.assertEqual(nba["x-nba-stats-origin"], "stats")
        self.assertEqual(nba["x-nba-stats-token"], "true")

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
        self.assertEqual(result["runner_probe"]["reachable_routes"],[])

    def test_health_surfaces_gamebook_reference_progress(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"gamebook_reference").mkdir()
            (root/"gamebook_reference"/"stat_pack.json").write_text(
                '{"role":"ALTERNATE_REFERENCE_ONLY","season":"2026-27",'
                '"date_to":"10/25/2026","gamebooks":42,"expected_gamebooks":43,'
                '"missing_gamebooks":[{"reference_id":"x"}],'
                '"gamebook_completeness":0.9767,"collection_complete":false,'
                '"teams_with_games":30,"production_provider_authorized":false}'
            )
            result=build(root)
        self.assertEqual(result["gamebook_reference"]["gamebooks"],42)
        self.assertEqual(result["gamebook_reference"]["missing_gamebooks"],1)
        self.assertFalse(result["gamebook_reference"]["production_provider_authorized"])

    def test_health_surfaces_canonical_parity_capture(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"canonical_stats_reference").mkdir()
            (root/"canonical_stats_reference"/"status.json").write_text(
                '{"checked_at":"2026-11-01T12:00:00+00:00","state":"READY_FOR_PARITY",'
                '"season":"2026-27","date_to":"10/31/2026","canonical_pack_available":true,'
                '"team_rows":30,"player_rows":480,"parity_attempted":true,'
                '"parity_state":"COMPARED","parity_review_ready":false,'
                '"production_provider_authorized":false}'
            )
            result=build(root)
        self.assertEqual(result["canonical_stats_reference"]["state"],"READY_FOR_PARITY")
        self.assertEqual(result["canonical_stats_reference"]["team_rows"],30)
        self.assertTrue(result["canonical_stats_reference"]["parity_attempted"])
        self.assertFalse(result["canonical_stats_reference"]["production_provider_authorized"])

    def test_outcomes_are_behind_provider_adapter(self):
        games=[ScheduleGame("g","2026-10-20","2026-10-20T23:00:00Z","Boston Celtics","New York Knicks",3,"Final",120,110)]
        finals=OfficialOutcomeProvider(fetcher=lambda: games).finals()
        self.assertEqual(finals["g"].home_score,120)

if __name__=="__main__":unittest.main()
