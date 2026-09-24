import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from nba.preseason_ops import run


READY_PROVIDER = {
    "schema":"pulsar-nba-provider-smoke-v2",
    "checked_at":"2026-09-24T07:00:00Z",
    "state":"READY","operational_ready":True,"providers":{}
}
BLOCKED_PROVIDER = {
    "schema":"pulsar-nba-provider-smoke-v2",
    "checked_at":"2026-09-24T07:00:00Z",
    "state":"BLOCKED","operational_ready":False,"providers":{}
}
READY_MARKET = {
    "schema":"pulsar-nba-market-smoke-v2",
    "checked_at":"2026-09-24T07:00:00Z",
    "request_count":1,"coverage_ready":True,
    "complete_pinnacle_events":1
}
BLOCKED_MARKET = {
    "schema":"pulsar-nba-market-smoke-v2",
    "checked_at":"2026-09-24T07:00:00Z",
    "request_count":1,"coverage_ready":False,
    "complete_pinnacle_events":0
}


class PreseasonOpsTests(unittest.TestCase):
    def _paths(self, root):
        root=Path(root)
        return {
            "output":str(root/"validation.json"),
            "provider_output":str(root/"provider.json"),
            "market_output":str(root/"market.json"),
            "live_output":str(root/"live.json"),
            "odds_budget_path":str(root/"budget.json"),
            "snapshot_root":str(root/"snapshots"),
        }

    def test_provider_block_saves_zero_paid_requests(self):
        market=Mock()
        live=Mock()
        with tempfile.TemporaryDirectory() as d:
            result=run(
                target_date="2026-10-05",
                provider_runner=lambda:BLOCKED_PROVIDER,
                market_runner=market,live_runner=live,**self._paths(d))
        self.assertEqual(result["status"],"PROVIDER_BLOCKED")
        self.assertEqual(result["odds_api_requests"],0)
        market.assert_not_called()
        live.assert_not_called()

    def test_missing_pinnacle_stops_before_rehearsal(self):
        live=Mock()
        with tempfile.TemporaryDirectory() as d:
            result=run(
                target_date="2026-10-05",
                provider_runner=lambda:READY_PROVIDER,
                market_runner=lambda **_:BLOCKED_MARKET,
                live_runner=live,**self._paths(d))
        self.assertEqual(result["status"],"MARKET_NOT_READY")
        self.assertEqual(result["odds_api_requests"],1)
        live.assert_not_called()

    def test_market_exception_is_fail_closed(self):
        def boom(**_):
            raise RuntimeError("quota unavailable")
        with tempfile.TemporaryDirectory() as d:
            result=run(
                target_date="2026-10-05",
                provider_runner=lambda:READY_PROVIDER,
                market_runner=boom,live_runner=Mock(),**self._paths(d))
        self.assertEqual(result["status"],"MARKET_ERROR")
        self.assertFalse(result["real_betting_authorized"])

    def test_green_chain_runs_preseason_only_and_writes_no_evidence(self):
        live=Mock(return_value={
            "status":"OK","games":[{"game_id":"g"}],
            "odds_api_requests":1,
            "paper_recording":{"added":0,"reason":"preseason_not_evidence"},
            "final_forecasts":{"added":0,"reason":"preseason_not_evidence"},
            "failures":[],
        })
        with tempfile.TemporaryDirectory() as d:
            result=run(
                target_date="2026-10-05",
                provider_runner=lambda:READY_PROVIDER,
                market_runner=lambda **_:READY_MARKET,
                live_runner=live,**self._paths(d))
        self.assertEqual(result["status"],"REHEARSAL_COMPLETE")
        self.assertEqual(result["odds_api_requests"],2)
        self.assertFalse(result["prospective_evidence_eligible"])
        kwargs=live.call_args.kwargs
        self.assertEqual(kwargs["operating_mode"],"preseason")

    def test_preseason_evidence_write_is_safety_violation(self):
        live=Mock(return_value={
            "status":"OK","games":[{"game_id":"g"}],"odds_api_requests":1,
            "paper_recording":{"added":1},"final_forecasts":{"added":0},
            "failures":[],
        })
        with tempfile.TemporaryDirectory() as d:
            result=run(
                target_date="2026-10-05",
                provider_runner=lambda:READY_PROVIDER,
                market_runner=lambda **_:READY_MARKET,
                live_runner=live,**self._paths(d))
        self.assertEqual(result["status"],"SAFETY_VIOLATION")


if __name__=="__main__":
    unittest.main()
