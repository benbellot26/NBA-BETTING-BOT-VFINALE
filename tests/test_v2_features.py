import unittest

from nba.model import GameContext, ScoreProjection, TeamMetrics
from nba.rotations import RotationPlayer
from nba.v2_features import (
    FEATURE_NAMES,
    FORBIDDEN_FEATURE_TOKENS,
    build_feature_snapshot,
    validate_feature_payload,
)


class V2FeatureTests(unittest.TestCase):
    def test_feature_contract_is_market_free(self):
        self.assertTrue(FEATURE_NAMES)
        for name in FEATURE_NAMES:
            self.assertFalse(any(token in name.lower() for token in FORBIDDEN_FEATURE_TOKENS))

    def test_builds_complete_numeric_snapshot(self):
        rotation = [RotationPlayer(str(i), str(i), 30.0, 1.0, -0.5, 0.2)
                    for i in range(8)]
        home = TeamMetrics("H", 119, 112, 100)
        away = TeamMetrics("A", 114, 116, 98)
        context = GameContext(
            "g", "2026-11-01", "2026-11-01T20:00:00+00:00", "H", "A",
            home_rest_days=2, away_rest_days=1, away_b2b=True,
        )
        score = ScoreProjection(
            "g", "2026-11-01", context.analyzed_at, "H", "A",
            118, 112, 99, 6, 230, 11.5, 17.0,
        )
        windows = {
            0: [{"TEAM_NAME": "H", "OFF_RATING": 118, "DEF_RATING": 112, "PACE": 99},
                {"TEAM_NAME": "A", "OFF_RATING": 114, "DEF_RATING": 116, "PACE": 98}],
            30: [{"TEAM_NAME": "H", "OFF_RATING": 119, "DEF_RATING": 111, "PACE": 100}],
            15: [], 10: [], 5: [{"TEAM_NAME": "H", "OFF_RATING": 123, "DEF_RATING": 109, "PACE": 101}],
        }
        payload = build_feature_snapshot(
            home=home, away=away, context=context,
            home_rotation=rotation, away_rotation=rotation,
            score_projection=score, advanced_windows=windows,
        )
        validated = validate_feature_payload(payload)
        self.assertEqual(set(validated["features"]), set(FEATURE_NAMES))
        self.assertEqual(validated["features"]["baseline_margin"], 6.0)
        self.assertEqual(validated["features"]["away_b2b"], 1.0)
        self.assertEqual(validated["features"]["home_ortg_season"], 118.0)
        self.assertEqual(validated["features"]["home_ortg_last5"], 123.0)
        # Missing recent windows fall back to that team's season PIT row.
        self.assertEqual(validated["features"]["away_ortg_last5"], 114.0)
        self.assertEqual(len(FEATURE_NAMES), 78)


if __name__ == "__main__":
    unittest.main()
