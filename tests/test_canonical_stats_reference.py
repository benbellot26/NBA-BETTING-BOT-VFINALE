import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nba.canonical_stats_reference import run


def canonical_pack():
    teams = [
        {
            "TEAM_NAME": f"Team {i}",
            "OFF_RATING": 115.0,
            "DEF_RATING": 114.0,
            "PACE": 99.0,
            "EFG_PCT": 0.55,
            "TM_TOV_PCT": 13.0,
            "OREB_PCT": 0.25,
        }
        for i in range(30)
    ]
    players = [
        {
            "TEAM_ID": 100 + i // 4,
            "PLAYER_NAME": f"Player {i}",
            "MIN": 24.0,
            "USG_PCT": 0.20,
        }
        for i in range(120)
    ]
    return {
        "season": "2026-27",
        "date_to": "11/30/2026",
        "observed_at": "2026-12-01T12:00:00+00:00",
        "advanced_windows": {
            window: [dict(row) for row in teams]
            for window in (0, 30, 15, 10, 5)
        },
        "base_season": [
            {"TEAM_NAME": f"Team {i}", "FGA": 90, "FTA": 22.5, "FG3A": 36}
            for i in range(30)
        ],
        "player_season": [
            {"TEAM_ID": row["TEAM_ID"], "PLAYER_NAME": row["PLAYER_NAME"], "MIN": row["MIN"]}
            for row in players
        ],
        "player_recent": [
            {"TEAM_ID": row["TEAM_ID"], "PLAYER_NAME": row["PLAYER_NAME"], "MIN": 25.0}
            for row in players
        ],
        "player_advanced": players,
        "snapshot": {"sha256": "a" * 64, "source": "stats.nba.com"},
    }


class CanonicalStatsReferenceTests(unittest.TestCase):
    def test_success_writes_reference_without_authority(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            output = root / "canonical.json"
            status = root / "status.json"
            with patch(
                "nba.canonical_stats_reference.acquire_stat_pack",
                return_value=canonical_pack(),
            ):
                result = run(
                    target_date="2026-12-01",
                    output=str(output),
                    status_output=str(status),
                    alternate_path=str(root / "missing-alternate.json"),
                    parity_output=str(root / "parity.json"),
                    snapshot_root=str(root / "snapshots"),
                )
            saved = json.loads(output.read_text())
        self.assertEqual(result["state"], "READY_FOR_PARITY")
        self.assertTrue(result["canonical_pack_available"])
        self.assertEqual(result["parity_state"], "ALTERNATE_PACK_MISSING")
        self.assertFalse(result["production_provider_authorized"])
        self.assertEqual(saved["role"], "CANONICAL_PARITY_REFERENCE_ONLY")
        self.assertFalse(saved["predictive_authority"])
        self.assertFalse(saved["betting_certified"])
        self.assertEqual(len(saved["stat_pack_sha256"]), 64)

    def test_timeout_is_diagnostic_not_authority(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch(
                "nba.canonical_stats_reference.acquire_stat_pack",
                side_effect=RuntimeError("stats request TimeoutError"),
            ):
                result = run(
                    target_date="2026-12-01",
                    output=str(root / "canonical.json"),
                    status_output=str(root / "status.json"),
                    alternate_path=str(root / "alternate.json"),
                    parity_output=str(root / "parity.json"),
                    snapshot_root=str(root / "snapshots"),
                )
        self.assertEqual(result["state"], "TIMEOUT")
        self.assertFalse(result["canonical_pack_available"])
        self.assertFalse(result["production_provider_authorized"])
        self.assertFalse(result["betting_certified"])
        self.assertEqual(result["odds_api_requests"], 0)

    def test_preseason_sparse_stats_is_waiting_state(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch(
                "nba.canonical_stats_reference.acquire_stat_pack",
                side_effect=RuntimeError(
                    "NBA season/team/player stats not yet sufficiently available; "
                    "no backfill from future"
                ),
            ):
                result = run(
                    target_date="2026-09-28",
                    output=str(root / "canonical.json"),
                    status_output=str(root / "status.json"),
                    alternate_path=str(root / "alternate.json"),
                    parity_output=str(root / "parity.json"),
                    snapshot_root=str(root / "snapshots"),
                )
        self.assertEqual(result["state"], "WAITING_FOR_SEASON_DATA")


if __name__ == "__main__":
    unittest.main()
