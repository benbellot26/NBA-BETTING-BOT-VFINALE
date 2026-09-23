import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from nba.fixture_provider import DeterministicFixtureProvider
from nba.live_runtime import run as live_run
from nba.ops_health import build as build_health
from nba.research_session import run as session_run

DATE = "2026-11-15"


def args(root):
    root = Path(root)
    return dict(
        target_date=DATE,
        output=str(root / "live.json"),
        snapshot_root=str(root / "snapshots"),
        certification_path=str(root / "cert.json"),
        paper_path=str(root / "paper.jsonl"),
        forecasts_path=str(root / "forecasts.jsonl"),
        mode="preseason",
    )


class PreseasonOpsTests(unittest.TestCase):
    def test_preseason_never_writes_prospective_evidence(self):
        fixture = DeterministicFixtureProvider().capture(target_date=DATE)
        official = replace(fixture, provider_id="official-nba", role="PROSPECTIVE_SOURCE")
        with tempfile.TemporaryDirectory() as directory, patch(
            "nba.live_runtime.OfficialNBAProvider.capture", return_value=official
        ), patch("nba.live_runtime.fetch_nba_odds", return_value=[]):
            result = live_run(**args(directory))
        self.assertEqual(result["mode"], "preseason")
        self.assertFalse(result["evidence_eligible"])
        self.assertEqual(result["paper_recording"]["added"], 0)
        self.assertEqual(result["final_forecasts"]["added"], 0)
        self.assertFalse(Path(directory, "paper.jsonl").exists())
        self.assertFalse(Path(directory, "forecasts.jsonl").exists())

    def test_session_skips_close_capture_in_preseason(self):
        fake = {
            "status": "OK", "games": [], "failures": [],
            "evidence_eligible": False,
        }
        with tempfile.TemporaryDirectory() as directory, patch(
            "nba.research_session.run_live", return_value=fake
        ), patch("nba.research_session.capture_close") as close:
            result = session_run(target_date=DATE, mode="preseason", runtime_root=directory)
        close.assert_not_called()
        self.assertTrue(result["close"]["skipped"])

    def test_ops_health_stays_non_authorizing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "health").mkdir()
            (root / "health/provider_smoke.json").write_text(
                json.dumps({"ok": True}), encoding="utf-8")
            (root / "health/odds_market_smoke.json").write_text(
                json.dumps({"coverage_ok": True}), encoding="utf-8")
            report = build_health(root=root)
        self.assertTrue(report["rehearsal_ready"])
        self.assertFalse(report["live_operational"])
        self.assertFalse(report["real_betting_authorized"])


if __name__ == "__main__":
    unittest.main()
