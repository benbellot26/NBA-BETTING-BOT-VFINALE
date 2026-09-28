import unittest

from nba.gamebook import parse_final_box_text
from nba.gamebook_stats import build_reference_stat_pack
from nba.rotation_projection import project_rotation
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
            "parsed": parsed,
        }

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
