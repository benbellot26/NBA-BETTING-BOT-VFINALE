import json
import tempfile
import unittest
from pathlib import Path

from nba.research_readiness import build


class ResearchReadinessTests(unittest.TestCase):
    def test_matrix_surfaces_current_blockers_and_free_plan_skip(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"evidence").mkdir()
            (root/"gamebook_reference").mkdir()
            (root/"provider_shadow").mkdir()
            (root/"research").mkdir()
            (root/"provider_smoke.json").write_text(json.dumps({
                "state":"BLOCKED","operational_ready":False,
                "providers":{
                    "schedule":{"state":"OFFICIAL_PREGAME_FALLBACK"},
                    "stats":{"state":"TIMEOUT"},
                    "injuries":{"state":"NOT_PUBLISHED"},
                },
            }),encoding="utf-8")
            (root/"market_smoke.json").write_text(json.dumps({
                "availability_state":"PINNACLE_TARGET_EMPTY",
                "coverage_ready":False,"events":41,"pinnacle_events":0,
            }),encoding="utf-8")
            (root/"bookmaker_discovery.json").write_text(json.dumps({
                "pinnacle_present":False,"complete_consensus_events":20,
            }),encoding="utf-8")
            (root/"historical_pinnacle_probe.json").write_text(json.dumps({
                "state":"HISTORICAL_PROVIDER_ERROR",
                "provider_error_code":"HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN",
                "historical_pinnacle_available":False,
            }),encoding="utf-8")
            (root/"gamebook_reference"/"stat_pack.json").write_text(json.dumps({
                "gamebooks":0,"teams_with_games":0,
            }),encoding="utf-8")
            result=build(root)
            areas=result["areas"]
            self.assertEqual(areas["canonical_provider"]["state"],"BLOCKED")
            self.assertEqual(
                areas["current_pinnacle"]["state"],"PINNACLE_TARGET_EMPTY")
            self.assertEqual(
                areas["historical_pinnacle_research"]["state"],"PLAN_BLOCKED")
            self.assertTrue(
                areas["historical_pinnacle_research"]["requests_should_be_skipped"])
            self.assertEqual(
                areas["gamebook_provider_shadow"]["state"],
                "WAITING_FOR_SEASON_DATA",
            )
            self.assertEqual(
                areas["learned_v2"]["state"],"COLLECTING_TRAINING_DATA")
            self.assertFalse(result["live_betting_authorized"])
            self.assertFalse(result["betting_certified"])
            self.assertFalse(result["pinnacle_replacement_allowed"])


if __name__=="__main__":
    unittest.main()
