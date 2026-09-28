import json
import tempfile
import unittest
from pathlib import Path

from nba.stats_runner_matrix import merge


def report(runner, valid=None):
    valid=list(valid or [])
    return {
        "schema":"pulsar-nba-stats-route-transport-v1",
        "runner":runner,
        "valid_stats_routes":valid,
        "alternate_official_route_found":any(x!="stats_primary" for x in valid),
        "routes":[
            {"name":"stats_primary","state":"VALID_STATS_PAYLOAD" if "stats_primary" in valid else "TIMEOUT","elapsed_ms":10.0},
            {"name":"api_hub_stats_path","state":"HTTP_461","elapsed_ms":2.0},
        ],
    }


class StatsRunnerMatrixTests(unittest.TestCase):
    def test_finds_working_hosted_runner_without_authorizing_provider(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for i,value in enumerate((
                report("ubuntu-latest"),
                report("windows-latest",["stats_primary"]),
                report("macos-latest"),
            )):
                (root/f"{i}.json").write_text(json.dumps(value),encoding="utf-8")
            result=merge(root)
        self.assertTrue(result["hosted_runner_solution_found"])
        self.assertEqual(result["working_runners"],["windows-latest"])
        self.assertFalse(result["production_provider_authorized"])
        self.assertFalse(result["predictive_evidence_eligible"])
        self.assertEqual(result["odds_api_requests"],0)

    def test_missing_artifact_stays_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"ubuntu.json").write_text(
                json.dumps(report("ubuntu-latest")),encoding="utf-8"
            )
            result=merge(root)
        self.assertEqual(result["runners"]["windows-latest"]["state"],"MISSING_ARTIFACT")
        self.assertFalse(result["hosted_runner_solution_found"])


if __name__=="__main__":
    unittest.main()
