import unittest
from unittest.mock import patch

from nba.stats_page_probe import _scan, run


class StatsPageProbeTests(unittest.TestCase):
    def test_scan_records_only_structural_signals(self):
        html='<html><script id="__NEXT_DATA__" type="application/json">{}</script>OFF_RATING TEAM_NAME rowSet</html>'
        result=_scan(html)
        self.assertEqual(result["marker_counts"]["OFF_RATING"],1)
        self.assertEqual(result["marker_counts"]["TEAM_NAME"],1)
        self.assertEqual(result["marker_counts"]["rowSet"],1)
        self.assertTrue(result["structured_payload_signal"])
        self.assertEqual(len(result["sha256"]),64)
        self.assertNotIn("html",result)

    def test_probe_is_diagnostic_only(self):
        html='<script>self.__next_f.push([1,"TEAM_NAME OFF_RATING PLAYER_NAME"])</script>'
        with patch("nba.stats_page_probe.get_text",return_value=html) as get:
            report=run(season="2025-26")
        self.assertEqual(get.call_count,4)
        self.assertEqual(report["role"],"NETWORK_DIAGNOSTIC_ONLY")
        self.assertFalse(report["predictive_evidence_eligible"])
        self.assertFalse(report["production_provider_authorized"])
        self.assertEqual(report["odds_api_requests"],0)
        self.assertTrue(report["all_pages_reachable"])
        self.assertTrue(report["structured_candidate_for_reference_parser"])

    def test_partial_page_failure_never_authorizes_reference_parser(self):
        calls=[RuntimeError("HTTP 403"),"<html>ok</html>","<html>ok</html>","<html>ok</html>"]
        with patch("nba.stats_page_probe.get_text",side_effect=calls):
            report=run(season="2025-26")
        self.assertFalse(report["all_pages_reachable"])
        self.assertFalse(report["structured_candidate_for_reference_parser"])


if __name__=="__main__":
    unittest.main()
