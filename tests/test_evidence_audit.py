import unittest

from nba import MODEL_GENERATION
from nba.evidence_audit import audit_records
from nba.lineage import build_input_manifest
from nba.model import GameContext, TeamMetrics
from nba.rotations import RotationPlayer
from nba.settlement import settle_candidate


def corpus():
    context = GameContext("g", "2026-11-15", "2026-11-15T22:00:00Z",
                          "Boston Celtics", "New York Knicks", phase="FINAL")
    manifest = build_input_manifest(
        context=context,
        home=TeamMetrics("Boston Celtics", 118, 111, 99),
        away=TeamMetrics("New York Knicks", 115, 113, 98),
        home_rotation=[RotationPlayer("h", "H", 240)],
        away_rotation=[RotationPlayer("a", "A", 240)],
        stats_snapshot_sha256="a" * 64,
        stats_observed_at="2026-11-15T20:00:00Z",
        injury_snapshot_sha256="b" * 64,
        injury_reported_at="2026-11-15T21:30:00Z",
    )
    forecast = {
        "entry_key": "g|pulsar-nba-v1-structural|FINAL",
        "game_id": "g", "role": "PIT_FINAL_FORECAST",
        "model_generation": MODEL_GENERATION,
        "source_snapshot_sha256": manifest["sha256"],
        "source_snapshot_at": manifest["source_snapshot_at"],
        "forecast_at": context.analyzed_at,
        "tipoff_at": "2026-11-15T22:20:00Z",
        "input_manifest": manifest,
    }
    paper = {
        "entry_key": "g|ML|home_ml", "game_id": "g", "market": "ML",
        "selection": "home_ml", "status": "PAPER", "phase": "FINAL",
        "model_generation": MODEL_GENERATION,
        "source_snapshot_sha256": manifest["sha256"],
        "entry_at": context.analyzed_at, "commence_time": forecast["tipoff_at"],
        "price": 2.0, "stake_fraction": .01, "line": None,
    }
    outcome = {
        "game_id": "g", "source": "official_nba_schedule",
        "home_score": 116, "away_score": 111,
        "outcome_at": "2026-11-16T03:00:00Z",
    }
    settled = settle_candidate(paper, home_score=116, away_score=111)
    close = {
        "entry_key": paper["entry_key"], "game_id": "g", "market": "ML",
        "selection": "home_ml", "captured_at": "2026-11-15T22:19:00Z",
        "pinnacle_close_no_vig_probability": .52,
        "price_clv_comparable": True, "clv_pp": 2.0,
    }
    return forecast, paper, outcome, close, settled


class EvidenceAuditTests(unittest.TestCase):
    def test_valid_closed_paper_cohort(self):
        f, p, o, c, s = corpus()
        result = audit_records(forecasts=[f], paper=[p], outcomes=[o],
                               closes=[c], settled=[s])
        self.assertTrue(result["ok"], result["errors"])
        self.assertFalse(result["betting_certified"])
        self.assertEqual(result["counts"]["settled_entries"], 1)

    def test_future_forecast_rejected(self):
        f, p, o, c, s = corpus()
        f["forecast_at"] = "2026-11-15T22:21:00Z"
        result = audit_records(forecasts=[f], paper=[p], outcomes=[o],
                               closes=[c], settled=[s])
        self.assertFalse(result["ok"])
        self.assertTrue(any("forecast" in e for e in result["errors"]))

    def test_changed_report_fingerprint_rejected(self):
        f, p, o, c, s = corpus()
        f["source_snapshot_sha256"] = "f" * 64
        result = audit_records(forecasts=[f], paper=[p], outcomes=[o],
                               closes=[c], settled=[s])
        self.assertFalse(result["ok"])

    def test_clv_after_tip_rejected(self):
        f, p, o, c, s = corpus()
        c["captured_at"] = "2026-11-15T22:21:00Z"
        result = audit_records(forecasts=[f], paper=[p], outcomes=[o],
                               closes=[c], settled=[s])
        self.assertTrue(any("close" in e for e in result["errors"]))

    def test_fabricated_profit_rejected(self):
        f, p, o, c, s = corpus()
        s["profit_bankroll_fraction"] = .99
        result = audit_records(forecasts=[f], paper=[p], outcomes=[o],
                               closes=[c], settled=[s])
        self.assertTrue(any("settlement" in e for e in result["errors"]))

    def test_empty_corpus_is_not_certification(self):
        result = audit_records(forecasts=[], paper=[], outcomes=[],
                               closes=[], settled=[])
        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["final_forecasts"], 0)
        self.assertFalse(result["betting_certified"])


if __name__ == "__main__":
    unittest.main()
