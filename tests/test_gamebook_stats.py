import unittest
from unittest.mock import patch

from nba.communications_schedule import ReferenceScheduleGame
from nba.gamebook import parse_final_box_text
from nba.gamebook_stats import (_json_sha256, _validate_cached, build_reference_stat_pack,\n                                reference_schedule_from_games, resolve_gamebook_schedule)
from nba.rotation_projection import project_rotation
from nba.schedule import ScheduleGame
from nba.teams import team_info
from test_gamebook import FINAL_BOX


class GamebookStatPackTests(unittest.TestCase):
    def _record(self):
        parsed = parse_final_box_text(
            FINAL_BOX,
            expected_away="Golden State Warriors",
            expected_home="Detroit Pistons",
        )
        return {
            "schema": "pulsar-nba-gamebook-cache-v1",
            "source": "NBA_OFFICIAL_SCORERS_REPORT",
            "role": "ALTERNATE_REFERENCE_ONLY",
            "reference_id": "g1",
            "game_date": "2026-03-20",
            "away": "Golden State Warriors",
            "home": "Detroit Pistons",
            "pdf_sha256": "a" * 64,
            "parsed_sha256": _json_sha256(parsed),
            "parsed": parsed,
        }

    def test_current_schedule_reference_preserves_preseason_game_id(self):
        game = ScheduleGame(
            "0012600010", "2026-10-06", "2026-10-07T02:00:00Z",
            "Golden State Warriors", "Los Angeles Lakers", 1, "10:00 pm ET",
        )
        rows = reference_schedule_from_games([game])
        self.assertEqual(rows[0].reference_id, "0012600010")
        self.assertEqual(rows[0].away, "Los Angeles Lakers")
        self.assertEqual(rows[0].home, "Golden State Warriors")

    def test_gamebook_schedule_prefers_full_current_schedule(self):
        games = [
            ScheduleGame(
                str(index), "2026-10-06", "2026-10-07T02:00:00Z",
                "Golden State Warriors", "Los Angeles Lakers", 1, "Scheduled",
            )
            for index in range(1000)
        ]
        with patch("nba.gamebook_stats.fetch_schedule", return_value=games), patch(
            "nba.gamebook_stats.fetch_reference_schedule"
        ) as fallback:
            rows = resolve_gamebook_schedule(season="2026-27")
        self.assertEqual(len(rows), 1000)
        fallback.assert_not_called()

    def test_empty_preseason_history_is_complete_not_missing(self):
        pack = build_reference_stat_pack(
            season="2026-27",
            target_date="2026-09-28",
            gamebooks=[],
            missing=[],
        )
        self.assertEqual(pack["expected_gamebooks"], 0)
        self.assertEqual(pack["gamebook_completeness"], 1.0)
        self.assertTrue(pack["collection_complete"])
        self.assertEqual(len(pack["gamebook_manifest_sha256"]), 64)
        self.assertEqual(len(pack["stat_pack_sha256"]), 64)

    def test_builds_team_windows_and_player_rows(self):
        pack = build_reference_stat_pack(
            season="2025-26",
            target_date="2026-03-21",
            gamebooks=[self._record()],
            missing=[],
        )
        self.assertEqual(pack["role"], "ALTERNATE_REFERENCE_ONLY")
        self.assertFalse(pack["production_provider_authorized"])
        self.assertEqual(pack["date_to"], "03/20/2026")
        self.assertEqual(pack["gamebook_completeness"], 1.0)
        self.assertEqual(pack["teams_with_games"], 2)

        season_rows = {row["TEAM_NAME"]: row for row in pack["advanced_windows"][0]}
        gsw = season_rows["Golden State Warriors"]
        det = season_rows["Detroit Pistons"]
        self.assertEqual(gsw["GP"], 1)
        self.assertEqual(det["GP"], 1)
        self.assertAlmostEqual(gsw["EFG_PCT"], (35 + 0.5 * 12) / 76, places=9)
        self.assertGreater(gsw["OFF_RATING"], 80)
        self.assertLess(gsw["OFF_RATING"], 140)
        self.assertGreater(gsw["PACE"], 80)
        self.assertLess(gsw["PACE"], 120)

        base = {row["TEAM_NAME"]: row for row in pack["base_season"]}
        self.assertEqual(base["Golden State Warriors"]["FGA"], 76.0)
        self.assertEqual(base["Detroit Pistons"]["FG3A"], 21.0)
        usage = [row["USG_PCT"] for row in pack["player_advanced"]]
        self.assertTrue(usage)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in usage))
        self.assertEqual(pack["usage_scale"], "fraction_0_to_1")
        self.assertEqual(pack["possession_method"], "symmetric_boxscore_estimate")

    def test_cached_gamebook_is_bound_to_schedule_identity(self):
        record = self._record()
        game = ReferenceScheduleGame(
            reference_id="g1",
            schedule_number=1,
            game_date="2026-03-20",
            commence_time="2026-03-20T23:00:00+00:00",
            team1="Golden State Warriors",
            team2="Detroit Pistons",
            relation="at",
            away="Golden State Warriors",
            home="Detroit Pistons",
            neutral_site=False,
        )
        _validate_cached(record, game)
        record["game_date"] = "2026-03-19"
        with self.assertRaisesRegex(ValueError, "date mismatch"):
            _validate_cached(record, game)

    def test_cached_gamebook_rejects_tampered_parsed_payload(self):
        record = self._record()
        record["parsed"]["away_score"] += 1
        with self.assertRaisesRegex(ValueError, "parsed checksum"):
            _validate_cached(record)

    def test_cached_gamebook_rejects_invalid_pdf_digest(self):
        record = self._record()
        record["pdf_sha256"] = "not-a-sha"
        with self.assertRaisesRegex(ValueError, "digest"):
            _validate_cached(record)

    def test_derived_player_rows_are_rotation_compatible(self):
        pack = build_reference_stat_pack(
            season="2025-26",
            target_date="2026-03-21",
            gamebooks=[self._record()],
            missing=[],
        )
        tid = team_info("Golden State Warriors").team_id
        rotation = project_rotation(
            tid,
            season_base=pack["player_season"],
            recent_base=pack["player_recent"],
            season_advanced=pack["player_advanced"],
            team_ortg=115.0,
            team_drtg=115.0,
        )
        self.assertGreaterEqual(len(rotation), 6)
        self.assertAlmostEqual(sum(row.minutes for row in rotation), 240.0, places=6)
        # Gamebook fallback deliberately avoids inventing player on/off impact.
        self.assertTrue(all(abs(row.offensive_impact) <= 3.5 for row in rotation))
        self.assertTrue(all(abs(row.defensive_impact) <= 3.5 for row in rotation))


if __name__ == "__main__":
    unittest.main()
