import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nba.preseason_check import check


ROOT = Path(__file__).resolve().parents[1]


class PreseasonCheckTests(unittest.TestCase):
    def test_offline_readiness_stays_explicitly_non_operational(self):
        with patch("nba.provider_http.urlopen", side_effect=AssertionError("network forbidden")), patch(
            "nba.acquisition.fetch_nba_odds", side_effect=AssertionError("odds forbidden")
        ), patch("nba.providers.fetch_schedule", side_effect=AssertionError("schedule forbidden")):
            result = check(root=ROOT)
        self.assertTrue(result["software_ready"], result["errors"])
        self.assertFalse(result["live_operational"])
        self.assertFalse(result["real_betting_authorized"])
        self.assertEqual(result["odds_api_requests"], 0)
        self.assertEqual(result["upstream_providers"], "NOT_TESTED_IN_OFFLINE_CHECK")

    def test_missing_workflow_gate_fails_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / "data/nba_betting_certification.json").write_text(
                (ROOT / "data/nba_betting_certification.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / ".github/workflows/live-research.yml").write_text(
                "name: unsafe live workflow", encoding="utf-8",
            )
            (root / ".github/workflows/daily-evidence.yml").write_text(
                "if: NBA_LIVE_ENABLED == 'true'", encoding="utf-8",
            )
            report = check(root=root)
        self.assertFalse(report["software_ready"])
        self.assertFalse(report["checks"]["live_workflow_gate_present"])

    def test_network_workflows_keep_configurable_runner_fallback(self):
        result = check(root=ROOT)
        self.assertTrue(result["checks"]["data_runner_portable"])

    def test_source_controlled_certification_must_remain_false(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / ".github" / "workflows").mkdir(parents=True)
            cert = json.loads((ROOT / "data/nba_betting_certification.json").read_text())
            cert["certified"] = True
            (root / "data/nba_betting_certification.json").write_text(json.dumps(cert))
            for name in ("live-research.yml", "daily-evidence.yml"):
                (root / ".github" / "workflows" / name).write_text(
                    "if: NBA_LIVE_ENABLED == 'true'", encoding="utf-8")
            report = check(root=root)
        self.assertFalse(report["software_ready"])
        self.assertFalse(report["checks"]["source_certification_locked"])


if __name__ == "__main__":
    unittest.main()
