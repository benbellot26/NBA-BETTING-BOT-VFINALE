import unittest
from unittest.mock import patch

from nba.stats_backend_probe import _scan_text, run


class StatsBackendProbeTests(unittest.TestCase):
    def test_scan_counts_only_whitelisted_markers(self):
        value=_scan_text(
            "https://stats.nba.com/stats/leaguedashteamstats "
            "api-hub.nba.com GraphQL"
        )
        self.assertEqual(value["stats_nba_host"],1)
        self.assertEqual(value["api_hub_host"],1)
        self.assertEqual(value["league_dash_team"],1)
        self.assertEqual(value["graphql"],1)

    def test_probe_never_authorizes_provider(self):
        html='<script src="/_next/static/chunks/a.js"></script>'
        js=(
            'fetch("https://api-hub.nba.com/stats/leaguedashteamstats");'
            'const x="cumestatsteam";'
        )
        with patch(
            "nba.stats_backend_probe.get_text",side_effect=[html,js]
        ) as get:
            result=run(season="2025-26",max_scripts=4)
        self.assertEqual(get.call_count,2)
        self.assertEqual(result["role"],"NETWORK_DIAGNOSTIC_ONLY")
        self.assertFalse(result["predictive_evidence_eligible"])
        self.assertFalse(result["production_provider_authorized"])
        self.assertEqual(result["odds_api_requests"],0)
        self.assertIn("api-hub.nba.com",result["backend_hints"])
        self.assertIn("league_dash_team",result["endpoint_hints"])
        self.assertIn("cume_stats_team",result["endpoint_hints"])
        self.assertNotIn("source",result["scripts"][0])


if __name__=="__main__":
    unittest.main()
