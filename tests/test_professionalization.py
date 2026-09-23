import tempfile
import unittest
from pathlib import Path

from nba.calibration import calibrate_probability, reliability
from nba.challengers import shadow_variants
from nba.data_quality import assess
from nba.injury_report import InjuryRecord, latest_point_in_time
from nba.model import ScoreProjection
from nba.portfolio_correlation import apply_correlation_cap
from nba.research_registry import register


class ProfessionalizationTests(unittest.TestCase):
    def test_injury_pit(self):
        rows=[InjuryRecord("1","A","BOS","QUESTIONABLE","2026-10-01T10:00:00Z"),InjuryRecord("1","A","BOS","OUT","2026-10-01T12:00:00Z")]
        self.assertEqual(latest_point_in_time(rows,cutoff="2026-10-01T11:00:00Z")["1"].status,"QUESTIONABLE")

    def test_quality_fail_closed(self):
        q=assess(analyzed_at="2026-10-01T12:00:00Z",team_stats_at="2026-09-29T12:00:00Z",injury_report_at="2026-10-01T11:00:00Z",odds_at="2026-10-01T11:59:00Z")
        self.assertFalse(q["eligible"])

    def test_calibration(self):
        cells=reliability([(.55,1)]*60+[(.55,0)]*40)
        p,used=calibrate_probability(.55,cells,minimum_cell_n=50)
        self.assertTrue(used); self.assertGreater(p,.55)

    def test_registry_append_only(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"registry.jsonl"
            register(p,experiment_id="X",hypothesis="h",spec={"a":1},train_period="a",validation_period="b",primary_metric="brier",success_rule="lower",minimum_sample=100,stopping_rule="fixed",promotion_scope="shadow")
            with self.assertRaises(ValueError): register(p,experiment_id="X",hypothesis="h",spec={"a":2},train_period="a",validation_period="b",primary_metric="brier",success_rule="lower",minimum_sample=100,stopping_rule="fixed",promotion_scope="shadow")

    def test_correlation_cap(self):
        rows=apply_correlation_cap([{"game_id":"g","selection":"home_ml","stake_fraction":.01},{"game_id":"g","selection":"home_spread","stake_fraction":.01}])
        self.assertLessEqual(sum(r["stake_fraction"] for r in rows),.0125+1e-12)

    def test_challengers_shadow(self):
        p=ScoreProjection("g","d","a","H","A",118,112,99,6,230)
        out=shadow_variants(p)
        self.assertEqual(out["referee"]["role"],"SHADOW")

if __name__=="__main__": unittest.main()
