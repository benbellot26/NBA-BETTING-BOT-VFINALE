import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nba.health_report import build
from nba.provider_smoke import _classify_failure, run as provider_run
from nba.readiness_gate import assess


NOW="2026-09-24T06:00:00+00:00"


class ReadinessGateTests(unittest.TestCase):
    def test_failure_classification_separates_blocked_timeout_and_publication(self):
        self.assertEqual(_classify_failure(RuntimeError("HTTP 403")), "ACCESS_BLOCKED")
        self.assertEqual(_classify_failure(RuntimeError("HTTP 404"), source="injuries"), "NOT_PUBLISHED")
        self.assertEqual(_classify_failure(RuntimeError("HTTP 404"), source="stats"), "UNAVAILABLE")
        self.assertEqual(_classify_failure(RuntimeError("TimeoutError")), "TIMEOUT")
    def test_old_market_schema_cannot_satisfy_readiness(self):
        provider={"schema":"pulsar-nba-provider-smoke-v2",
                  "checked_at":"2026-09-24T05:00:00Z","state":"READY",
                  "operational_ready":True,"providers":{}}
        market={"schema":"pulsar-nba-market-smoke-v1",
                "checked_at":"2026-09-24T05:30:00Z","coverage_ready":True,
                "complete_pinnacle_events":1}
        result=assess(provider=provider,market=market,at=NOW)
        self.assertFalse(result["ready_for_real_rehearsal"])
        self.assertIn("market_smoke_schema_unsupported",result["failures"])

        self.assertEqual(
            _classify_failure(RuntimeError(
                "official NBA injury page exposed no timestamped PDF report")),
            "NOT_PUBLISHED")

    def test_fresh_ready_provider_and_market_pass_rehearsal_gate(self):
        provider={"schema":"pulsar-nba-provider-smoke-v2","checked_at":"2026-09-24T05:00:00Z","state":"READY",
                  "operational_ready":True,"providers":{}}
        market={"schema":"pulsar-nba-market-smoke-v2","checked_at":"2026-09-24T05:30:00Z","coverage_ready":True,
                "complete_pinnacle_events":3}
        result=assess(provider=provider,market=market,at=NOW,max_age_hours=24)
        self.assertTrue(result["ready_for_real_rehearsal"])
        self.assertFalse(result["real_betting_authorized"])

    def test_waiting_for_publication_is_not_operational(self):
        provider={"checked_at":"2026-09-24T05:00:00Z",
                  "state":"WAITING_FOR_PUBLICATION","operational_ready":False,
                  "providers":{"injuries":{"state":"NOT_PUBLISHED"}}}
        market={"checked_at":"2026-09-24T05:30:00Z","coverage_ready":True,
                "complete_pinnacle_events":1}
        result=assess(provider=provider,market=market,at=NOW)
        self.assertFalse(result["ready_for_real_rehearsal"])
        self.assertIn("provider_not_operational:WAITING_FOR_PUBLICATION",
                      result["failures"])

    def test_stale_market_diagnostic_blocks_rehearsal_gate(self):
        provider={"checked_at":"2026-09-24T05:00:00Z","state":"READY",
                  "operational_ready":True,"providers":{}}
        market={"checked_at":"2026-09-22T00:00:00Z","coverage_ready":True,
                "complete_pinnacle_events":2}
        result=assess(provider=provider,market=market,at=NOW,max_age_hours=24)
        self.assertFalse(result["ready_for_real_rehearsal"])
        self.assertTrue(any("market_smoke_stale" in x for x in result["failures"]))

    def test_provider_smoke_marks_sparse_current_stats_historical_only(self):
        with patch("nba.provider_smoke.fetch_schedule",return_value=[object()]*1000), patch(
            "nba.provider_smoke.team_stats",
            side_effect=[[{"TEAM_NAME":"x"}]*10,[{"TEAM_NAME":"x"}]*30]
        ), patch("nba.provider_smoke.fetch_reference_schedule",return_value=[]), patch("nba.provider_smoke.fetch_latest_report",
                 return_value={"team_status":{"x":"SUBMITTED"},
                               "record_count":0,"reported_at":"2026-09-24T05:00:00Z"}):
            result=provider_run()
        self.assertEqual(result["providers"]["stats"]["state"],"HISTORICAL_ONLY")
        self.assertFalse(result["providers"]["stats"]["operational_ready"])
        self.assertEqual(result["state"],"WAITING_FOR_PUBLICATION")

    def test_health_distinguishes_waiting_from_hard_provider_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"provider_smoke.json").write_text(
                '{"checked_at":"2026-09-24T05:00:00Z","state":"WAITING_FOR_PUBLICATION","operational_ready":false,"providers":{}}'
            )
            report=build(root,at=NOW)
        self.assertEqual(report["state"],"WAITING_FOR_PUBLICATION")
        self.assertTrue(report["diagnostics"]["provider_fresh"])


if __name__=="__main__":
    unittest.main()
