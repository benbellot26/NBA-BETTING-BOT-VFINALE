import unittest
from dataclasses import replace

from nba.lineage import build_input_manifest, validate_manifest
from nba.model import GameContext, TeamMetrics
from nba.rotations import RotationPlayer
from nba.settlement import aggregate, settle_candidate


class LineageAndSettlementTests(unittest.TestCase):
    def setUp(self):
        self.context = GameContext(
            "game1", "2026-11-15", "2026-11-15T22:00:00Z",
            "Boston Celtics", "New York Knicks",
        )
        self.home = TeamMetrics("Boston Celtics", 117, 112, 99)
        self.away = TeamMetrics("New York Knicks", 114, 111, 98)
        self.home_rotation = [RotationPlayer("1", "H", 240)]
        self.away_rotation = [RotationPlayer("2", "A", 240)]
        self.kwargs = dict(
            context=self.context, home=self.home, away=self.away,
            home_rotation=self.home_rotation, away_rotation=self.away_rotation,
            stats_snapshot_sha256="a" * 64,
            stats_observed_at="2026-11-15T20:00:00Z",
            injury_snapshot_sha256="b" * 64,
            injury_reported_at="2026-11-15T21:30:00Z",
        )

    def test_identical_predictive_inputs_have_identical_manifest(self):
        first = build_input_manifest(**self.kwargs)
        second = build_input_manifest(**self.kwargs)
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(first["source_snapshot_at"], "2026-11-15T21:30:00+00:00")
        self.assertEqual(validate_manifest(first)["sha256"], first["sha256"])

    def test_injury_or_rotation_changes_invalidate_fingerprint(self):
        baseline = build_input_manifest(**self.kwargs)["sha256"]
        injury = build_input_manifest(
            **(self.kwargs | {"injury_snapshot_sha256": "c" * 64}))
        rotated = build_input_manifest(
            **(self.kwargs | {"home_rotation": [RotationPlayer("1", "H", 238),
                                                RotationPlayer("3", "B", 2)]}))
        self.assertNotEqual(baseline, injury["sha256"])
        self.assertNotEqual(baseline, rotated["sha256"])

    def test_input_cannot_be_observed_in_future(self):
        with self.assertRaisesRegex(ValueError, "after the analysis"):
            build_input_manifest(
                **(self.kwargs | {"injury_reported_at": "2026-11-15T22:30:00Z"}))

    def test_checksum_rejects_modified_source(self):
        valid = build_input_manifest(**self.kwargs)
        modified = valid | {"home_rotation_sha256": "f" * 64}
        with self.assertRaisesRegex(ValueError, "checksum"):
            validate_manifest(modified)

    def test_spread_and_totals_must_supply_line(self):
        base = {"market": "SPREAD", "selection": "home_spread",
                "price": 1.91, "stake_fraction": .01}
        with self.assertRaisesRegex(ValueError, "line"):
            settle_candidate(base, home_score=110, away_score=109)
        with self.assertRaisesRegex(ValueError, "line"):
            settle_candidate(base | {"line": float("nan")},
                             home_score=110, away_score=109)

    def test_spread_push_is_not_fabricated_win(self):
        row = settle_candidate(
            {"market": "SPREAD", "selection": "home_spread", "line": -4,
             "price": 1.9, "stake_fraction": .01},
            home_score=114, away_score=110,
        )
        self.assertEqual(row["settlement"], "PUSH")
        self.assertEqual(row["profit_bankroll_fraction"], 0.0)

    def test_moneyline_settlement_and_paper_only_aggregate(self):
        entry = {"market": "ML", "selection": "away_ml",
                 "line": None, "price": 2.1, "stake_fraction": .01}
        row = settle_candidate(entry, home_score=115, away_score=116)
        self.assertEqual(row["settlement"], "WIN")
        self.assertAlmostEqual(row["profit_bankroll_fraction"], .011)
        self.assertEqual(aggregate([row])["role"], "PAPER_ONLY")

    def test_invalid_odds_and_scores_rejected(self):
        row = {"market": "ML", "selection": "home_ml",
               "price": float("nan"), "stake_fraction": .01}
        with self.assertRaisesRegex(ValueError, "price"):
            settle_candidate(row, home_score=115, away_score=110)
        row["price"] = 2.0
        with self.assertRaisesRegex(ValueError, "home_score"):
            settle_candidate(row, home_score=-1, away_score=110)


if __name__ == "__main__":
    unittest.main()
