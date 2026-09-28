import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from nba.communications_schedule import ReferenceScheduleGame
from nba.fixture_provider import DeterministicFixtureProvider
from nba.gamebook_shadow_runtime import run


class GamebookProviderShadowTests(unittest.TestCase):
    def _inputs(self):
        fixture = DeterministicFixtureProvider().capture(
            target_date="2026-11-15"
        )
        stats = dict(fixture.stats)
        stats.update({
            "role": "ALTERNATE_REFERENCE_ONLY",
            "production_provider_authorized": False,
            "source": "NBA_OFFICIAL_SCORERS_REPORT",
            "stat_pack_sha256": "b" * 64,
            "gamebook_manifest_sha256": "c" * 64,
            "gamebook_completeness": 1.0,
            "collection_complete": True,
            "gamebooks": 120,
            "teams_with_games": 30,
            "limitations": {
                "player_off_def_ratings": "team_neutral_baseline",
                "production_requires_parity_gate": True,
            },
        })
        ref = ReferenceScheduleGame(
            reference_id="nba-pr-2026-27-2026-11-15-1",
            schedule_number=1,
            game_date="2026-11-15",
            commence_time="2026-11-15T22:20:00+00:00",
            team1="New York Knicks",
            team2="Boston Celtics",
            relation="at",
            away="New York Knicks",
            home="Boston Celtics",
            neutral_site=False,
        )
        return stats, fixture.injuries, [ref]

    def test_records_shadow_only_forecast(self):
        stats, injuries, schedule = self._inputs()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            output = root / "forecasts.jsonl"
            status = root / "status.json"
            result = run(
                target_date="2026-11-15",
                output=str(output),
                status_output=str(status),
                snapshot_root=str(root / "snapshots"),
                now=dt.datetime(
                    2026, 11, 15, 22, 0, tzinfo=dt.timezone.utc
                ),
                reference_schedule=schedule,
                stat_pack=stats,
                injuries=injuries,
            )
            self.assertEqual(result["status"], "SHADOW_FORECASTS_RECORDED")
            self.assertEqual(result["added"], 1)
            row = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(row["role"], "ALTERNATE_PROVIDER_SHADOW")
            self.assertFalse(row["production_provider_authorized"])
            self.assertFalse(row["predictive_authority"])
            self.assertFalse(row["market_data_used"])
            self.assertFalse(row["betting_certified"])
            self.assertFalse(row["promoted"])
            self.assertNotIn("decision", row)
            self.assertNotIn("stake_fraction", row)
            self.assertEqual(row["gamebook_stat_pack_sha256"], "b" * 64)
            self.assertEqual(len(row["source_snapshot_sha256"]), 64)

    def test_incomplete_history_fails_closed(self):
        stats, injuries, schedule = self._inputs()
        stats["gamebook_completeness"] = 0.95
        stats["collection_complete"] = False
        stats["missing_gamebooks"] = [{"reference_id": "x"}]
        with tempfile.TemporaryDirectory() as d:
            result = run(
                target_date="2026-11-15",
                output=str(Path(d) / "forecasts.jsonl"),
                status_output=str(Path(d) / "status.json"),
                snapshot_root=str(Path(d) / "snapshots"),
                now=dt.datetime(
                    2026, 11, 15, 22, 0, tzinfo=dt.timezone.utc
                ),
                reference_schedule=schedule,
                stat_pack=stats,
                injuries=injuries,
            )
            self.assertEqual(result["status"], "INCOMPLETE_GAMEBOOK_HISTORY")
            self.assertEqual(result["added"], 0)

    def test_only_final_window_is_recorded(self):
        stats, injuries, schedule = self._inputs()
        with tempfile.TemporaryDirectory() as d:
            result = run(
                target_date="2026-11-15",
                output=str(Path(d) / "forecasts.jsonl"),
                status_output=str(Path(d) / "status.json"),
                snapshot_root=str(Path(d) / "snapshots"),
                now=dt.datetime(
                    2026, 11, 15, 20, 0, tzinfo=dt.timezone.utc
                ),
                reference_schedule=schedule,
                stat_pack=stats,
                injuries=injuries,
            )
            self.assertEqual(result["status"], "NO_ELIGIBLE_FINAL_WINDOW")
            self.assertEqual(result["added"], 0)


if __name__ == "__main__":
    unittest.main()
