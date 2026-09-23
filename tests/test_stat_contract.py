import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nba.live_runtime import run
from nba.schedule import ScheduleGame
from nba.stat_contract import validate_game_stat_pack, validate_team_stats
from nba.team_inputs import build_team_metrics


HOME = "Boston Celtics"
AWAY = "New York Knicks"


def fixture(*, games=8, windowed=False):
    teams = [
        {"TEAM_NAME": HOME, "TEAM_ID": 1610612738, "OFF_RATING": 118.0,
         "DEF_RATING": 112.0, "PACE": 99.0, "EFG_PCT": .55,
         "OREB_PCT": .26, "TM_TOV_PCT": 12.5, "GP": games},
        {"TEAM_NAME": AWAY, "TEAM_ID": 1610612752, "OFF_RATING": 115.0,
         "DEF_RATING": 114.0, "PACE": 98.0, "EFG_PCT": .53,
         "OREB_PCT": .25, "TM_TOV_PCT": 0.13, "GP": games},
    ]
    base = [{"TEAM_NAME": t["TEAM_NAME"], "TEAM_ID": t["TEAM_ID"],
             "FGA": 88.0, "FG3A": 36.0, "FTA": 22.0} for t in teams]
    players = []
    advanced_players = []
    for team in teams:
        for i in range(8):
            row = {
                "TEAM_ID": team["TEAM_ID"],
                "PLAYER_ID": team["TEAM_ID"] * 100 + i,
                "PLAYER_NAME": f"{team['TEAM_NAME']} Player {i}",
                "MIN": 30.0,
            }
            players.append(row)
            advanced_players.append({
                **row, "OFF_RATING": 116.0, "DEF_RATING": 114.0, "USG_PCT": .20,
            })
    windows = {0: teams}
    if windowed:
        windows.update({n: [{k: v for k, v in row.items()}
                            for row in teams] for n in (30, 15, 10, 5)})
    return {
        "season": "2026-27", "date_to": "11/14/2026",
        "observed_at": "2026-11-15T20:00:00Z",
        "advanced_windows": windows,
        "base_season": base,
        "player_season": players, "player_recent": players,
        "player_advanced": advanced_players,
    }


class StatContractTests(unittest.TestCase):
    def test_valid_percent_or_fraction_turnovers(self):
        pack = fixture(windowed=True)
        result = validate_game_stat_pack(pack, HOME, AWAY, strict_live=True)
        self.assertTrue(result["eligible"])
        self.assertAlmostEqual(result["teams"][HOME]["tov_rate"], .125)
        self.assertAlmostEqual(result["teams"][AWAY]["tov_rate"], .13)
        projected = build_team_metrics(
            HOME, advanced_windows=pack["advanced_windows"],
            base_season=pack["base_season"], home=True)
        self.assertAlmostEqual(projected.tov_pct, .125)

    def test_missing_efg_is_not_silently_replaced(self):
        pack = fixture()
        del pack["advanced_windows"][0][0]["EFG_PCT"]
        with self.assertRaisesRegex(ValueError, "missing EFG_PCT"):
            validate_game_stat_pack(pack, HOME, AWAY, strict_live=False)
        with self.assertRaisesRegex(ValueError, "missing EFG_PCT"):
            build_team_metrics(
                HOME, advanced_windows=pack["advanced_windows"],
                base_season=pack["base_season"])

    def test_invalid_base_or_duplicate_team_rejected(self):
        pack = fixture()
        pack["base_season"][0]["FG3A"] = 100
        with self.assertRaisesRegex(ValueError, "FG3A"):
            validate_game_stat_pack(pack, HOME, AWAY, strict_live=False)
        pack = fixture()
        pack["advanced_windows"][0].append(dict(pack["advanced_windows"][0][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_game_stat_pack(pack, HOME, AWAY, strict_live=False)

    def test_window_requirement_and_player_coverage(self):
        pack = fixture()
        with self.assertRaisesRegex(ValueError, "temporal windows"):
            validate_game_stat_pack(pack, HOME, AWAY, strict_live=True)
        pack = fixture(windowed=True)
        pack["player_recent"] = [row for row in pack["player_recent"]
                                 if row["TEAM_ID"] != 1610612752
                                 or row["PLAYER_ID"] % 100 < 4]
        with self.assertRaisesRegex(ValueError, "insufficient active"):
            validate_game_stat_pack(pack, HOME, AWAY, strict_live=True)

    def test_early_season_not_qualified(self):
        pack = fixture(games=3)
        with self.assertRaisesRegex(ValueError, "insufficient GP"):
            validate_team_stats(
                HOME, advanced_windows=pack["advanced_windows"],
                base_season=pack["base_season"], min_games=5)

    def test_live_runtime_does_not_spend_odds_on_bad_stats(self):
        game = ScheduleGame(
            "nba-test", "2026-11-15", "2026-11-15T23:00:00Z",
            HOME, AWAY, 1, "Scheduled",
        )
        bad = fixture(windowed=True)
        del bad["advanced_windows"][0][0]["PACE"]
        report = {
            "reported_at": "2026-11-15T21:20:00Z",
            "source_url": "https://official.nba.com/test.pdf",
            "records": [],
            "team_status": {
                f"2026-11-15|{HOME}": "SUBMITTED",
                f"2026-11-15|{AWAY}": "SUBMITTED",
            },
        }
        with tempfile.TemporaryDirectory() as d:
            with patch("nba.live_runtime.fetch_schedule", return_value=[game]), \
                 patch("nba.live_runtime.acquire_stat_pack", return_value=bad), \
                 patch("nba.live_runtime.fetch_latest_report", return_value=report), \
                 patch("nba.live_runtime.fetch_nba_odds") as odds:
                result = run(
                    target_date="2026-11-15",
                    output=str(Path(d) / "result.json"),
                    snapshot_root=str(Path(d) / "snapshots"),
                    paper_path=str(Path(d) / "paper.jsonl"),
                )
            odds.assert_not_called()
        self.assertEqual(result["status"], "NO_ANALYSIS")
        self.assertTrue(any("stat_contract" in f for f in result["failures"]))
        self.assertTrue(any("odds_skipped" in f for f in result["failures"]))


if __name__ == "__main__":
    unittest.main()
