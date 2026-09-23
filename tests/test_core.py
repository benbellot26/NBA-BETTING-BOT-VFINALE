import unittest

from nba.certification import certify
from nba.decision import evaluate_candidate
from nba.distribution import probability_surface
from nba.market import no_vig_pair
from nba.model import GameContext, ScoreProjection, TeamMetrics
from nba.performance import brier, calibration_ece, logloss, mae
from nba.rotations import RotationPlayer, redistribute_out_minutes, validate_rotation
from nba.staking import conservative_stake_fraction
from nba.structural import project_game


class CoreTests(unittest.TestCase):
    def test_probability_complements(self):
        p=ScoreProjection("g","2026-10-01","x","H","A",118,112,99,6,230,11.5,17)
        s=probability_surface(p,spread_line=-3.5,total_line=226.5)
        self.assertAlmostEqual(s.home_ml+s.away_ml,1)
        self.assertAlmostEqual(s.home_spread+s.away_spread,1)
        self.assertAlmostEqual(s.over+s.under,1)
        self.assertGreater(s.home_spread,.5)
        self.assertGreater(s.over,.5)

    def test_no_vig(self):
        a,b=no_vig_pair(1.91,1.91)
        self.assertAlmostEqual(a,.5); self.assertAlmostEqual(b,.5)

    def test_rotation_redistribution(self):
        rows=[RotationPlayer(str(i),str(i),30 if i<8 else 0,status="AVAILABLE") for i in range(8)]
        rows[0]=RotationPlayer("0","0",30,4,2,.3,"OUT")
        rows.append(RotationPlayer("8","8",0,0,0,0,"AVAILABLE"))
        out=redistribute_out_minutes(rows)
        self.assertAlmostEqual(sum(x.minutes for x in out),240,places=2)
        self.assertEqual(out[0].minutes,0)

    def test_structural_projection(self):
        h=TeamMetrics("H",119,113,100); a=TeamMetrics("A",114,116,98)
        c=GameContext("g","2026-10-01","x","H","A")
        p,meta=project_game(home=h,away=a,context=c)
        self.assertGreater(p.home_points,p.away_points)
        self.assertIn("pace",meta)

    def test_decision_fail_closed(self):
        row=evaluate_candidate(selection="home_spread",market="SPREAD",model_probability=.60,lower_probability=.55,price=1.95,sharp_probability=.52,certified=False,market_fresh=True)
        self.assertEqual(row["status"],"NO_BET")
        self.assertIn("market_not_certified",row["failures"])

    def test_staking(self):
        c={"status":"BET","lower_probability":.58,"price":1.95}
        self.assertLessEqual(conservative_stake_fraction(c,certified=True),.01)
        self.assertEqual(conservative_stake_fraction(c,certified=False),0)

    def test_metrics(self):
        self.assertAlmostEqual(brier(.6,1),.16)
        self.assertGreater(logloss(.6,1),0)
        self.assertGreaterEqual(calibration_ece([(.6,1),(.6,0)]),0)
        self.assertEqual(mae([1,2],[2,2]),.5)

    def test_certification_requires_evidence(self):
        c=certify({"games":10,"markets":{}})
        self.assertFalse(c["certified"])

if __name__ == "__main__": unittest.main()
