import json
import unittest
from unittest.mock import patch

from nba.provider_http import ProviderError
from nba.stats_route_transport_probe import _probe, run


def valid_payload():
    headers=["TEAM_ID","TEAM_NAME"]
    rows=[[i,f"Team {i}"] for i in range(30)]
    return json.dumps({"resultSet":{"headers":headers,"rowSet":rows}}).encode()


class StatsRouteTransportProbeTests(unittest.TestCase):
    def test_valid_stats_payload_is_detected(self):
        with patch("nba.stats_route_transport_probe.get_bytes",return_value=valid_payload()):
            row=_probe(
                "stats_primary",
                "https://stats.nba.com/stats/leaguedashteamstats",
                season="2025-26",
                timeout=1,
            )
        self.assertTrue(row["ok"])
        self.assertEqual(row["state"],"VALID_STATS_PAYLOAD")
        self.assertEqual(row["rows"],30)

    def test_http_status_is_safely_classified(self):
        error=ProviderError(
            "GET https://api-hub.nba.com/stats/leaguedashteamstats failed: HTTP 461"
        )
        with patch("nba.stats_route_transport_probe.get_bytes",side_effect=error):
            row=_probe(
                "api_hub_stats_path",
                "https://api-hub.nba.com/stats/leaguedashteamstats",
                season="2025-26",
                timeout=1,
            )
        self.assertFalse(row["ok"])
        self.assertEqual(row["state"],"HTTP_461")
        self.assertNotIn("?",row["error"])

    def test_run_never_authorizes_provider(self):
        error=ProviderError("GET https://stats.nba.com/stats/leaguedashteamstats failed: TimeoutError")
        with patch("nba.stats_route_transport_probe.get_bytes",side_effect=error):
            result=run(season="2025-26",timeout=1)
        self.assertEqual(result["candidate_count"],3)
        self.assertFalse(result["alternate_official_route_found"])
        self.assertFalse(result["predictive_evidence_eligible"])
        self.assertFalse(result["production_provider_authorized"])
        self.assertEqual(result["odds_api_requests"],0)


if __name__=="__main__":
    unittest.main()
