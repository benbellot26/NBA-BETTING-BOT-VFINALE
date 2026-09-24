import unittest
from unittest.mock import patch

from nba.runner_probe import run


class RunnerProbeTests(unittest.TestCase):
    def test_runner_probe_is_diagnostic_only_and_never_calls_odds(self):
        with patch("nba.runner_probe.get_json",return_value={"leagueSchedule":{}}), patch(
            "nba.runner_probe.get_text",return_value="<html>nba</html>"), patch(
            "nba.runner_probe.team_stats",return_value=[{"TEAM_NAME":"x"}]*30):
            report=run()
        self.assertEqual(report["role"],"NETWORK_DIAGNOSTIC_ONLY")
        self.assertFalse(report["predictive_evidence_eligible"])
        self.assertEqual(report["odds_api_requests"],0)
        self.assertEqual(len(report["reachable_routes"]),5)

    def test_runner_probe_records_failure_without_raising(self):
        with patch("nba.runner_probe.get_json",side_effect=RuntimeError("HTTP 403")), patch(
            "nba.runner_probe.get_text",return_value="ok"), patch(
            "nba.runner_probe.team_stats",return_value=[{"TEAM_NAME":"x"}]*30):
            report=run()
        self.assertFalse(report["probes"]["cdn_schedule_json"]["ok"])
        self.assertEqual(report["probes"]["cdn_schedule_json"]["state"],
                         "ACCESS_BLOCKED")


if __name__=="__main__":
    unittest.main()
