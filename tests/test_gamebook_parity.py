import unittest

from nba.gamebook_parity import assess


def pack(source: str, *, offset: float = 0.0):
    advanced = {}
    teams = []
    for i in range(30):
        teams.append({
            "TEAM_NAME": f"Team {i}",
            "OFF_RATING": 115.0 + offset,
            "DEF_RATING": 114.0 + offset,
            "PACE": 99.0 + offset,
            "EFG_PCT": 0.55 + offset * 0.001,
            "TM_TOV_PCT": 13.0 + offset,
            "OREB_PCT": 0.25 + offset * 0.001,
        })
    for window in (0, 30, 15, 10, 5):
        advanced[window] = [dict(row) for row in teams]
    players = [
        {
            "TEAM_ID": 100 + i // 4,
            "PLAYER_NAME": f"Player {i}",
            "MIN": 24.0 + offset,
            "USG_PCT": 20.0 + offset,
        }
        for i in range(120)
    ]
    result = {
        "season": "2026-27",
        "date_to": "11/30/2026",
        "advanced_windows": advanced,
        "player_season": players,
    }
    if source == "alternate":
        result.update({
            "schema": "pulsar-nba-gamebook-stat-pack-v1",
            "production_provider_authorized": False,
            "source": "NBA_OFFICIAL_SCORERS_REPORT",
        })
    return result


class GamebookParityTests(unittest.TestCase):
    def test_small_differences_are_manual_review_ready_only(self):
        result = assess(pack("canonical"), pack("alternate", offset=0.2))
        self.assertTrue(result["review_ready"])
        self.assertFalse(result["production_provider_authorized"])
        self.assertFalse(result["betting_certified"])
        self.assertEqual(result["role"], "MANUAL_REVIEW_ONLY")
        self.assertTrue(result["limitations"])

    def test_large_team_bias_blocks_review(self):
        result = assess(pack("canonical"), pack("alternate", offset=3.0))
        self.assertFalse(result["review_ready"])
        self.assertTrue(any("OFF_RATING" in item for item in result["failures"]))

    def test_alternate_cannot_claim_authority(self):
        alternate = pack("alternate")
        alternate["production_provider_authorized"] = True
        with self.assertRaisesRegex(ValueError, "forbidden authority"):
            assess(pack("canonical"), alternate)


if __name__ == "__main__":
    unittest.main()
