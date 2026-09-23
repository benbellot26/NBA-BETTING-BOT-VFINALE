import unittest

from nba.pit_bundle import ROLE, _digest, analyze_offline, pack, validate
from nba.schedule import ScheduleGame


def example():
    date = "2026-10-21"
    home = "Boston Celtics"
    away = "New York Knicks"
    schedule = [ScheduleGame("g", date, "2026-10-21T23:00:00Z",
                             home, away, 1, "Scheduled")]
    team_rows = [
        {"TEAM_NAME": home, "OFF_RATING": 118, "DEF_RATING": 111, "PACE": 99, "GP": 8, "EFG_PCT": .56, "OREB_PCT": .27, "TM_TOV_PCT": 12.5},
        {"TEAM_NAME": away, "OFF_RATING": 115, "DEF_RATING": 114, "PACE": 98, "GP": 8, "EFG_PCT": .53, "OREB_PCT": .25, "TM_TOV_PCT": 13.8},
    ]
    ids = ((1610612738, "Boston"), (1610612752, "New York"))
    players = []
    for team_id, prefix in ids:
        players.extend({"TEAM_ID": team_id, "PLAYER_ID": team_id * 100 + i,
                        "PLAYER_NAME": f"{prefix} Player {i}", "MIN": 30}
                       for i in range(8))
    stats = {"season": "2026-27", "date_to": "10/20/2026",
             "observed_at": "2026-10-21T21:50:00Z",
             "advanced_windows": {0: team_rows},
             "base_season": [{"TEAM_NAME": t["TEAM_NAME"], "FGA": 88, "FG3A": 35, "FTA": 22}
                             for t in team_rows],
             "player_season": players, "player_recent": players,
             "player_advanced": []}
    injuries = {"reported_at": "2026-10-21T21:55:00Z", "records": [],
                "team_status": {f"{date}|{home}": "SUBMITTED",
                                f"{date}|{away}": "SUBMITTED"}}
    return pack(target_date=date, season="2026-27",
                captured_at="2026-10-21T22:00:00Z", schedule=schedule,
                stats=stats, injuries=injuries)


class PitBundleTests(unittest.TestCase):
    def test_checksum_and_research_role(self):
        bundle = example()
        self.assertEqual(bundle["sha256"], _digest(bundle))
        result = analyze_offline(bundle, {"g": {"spread_line": -3.5, "total_line": 228.5}})
        self.assertEqual(result["role"], ROLE)
        self.assertFalse(result["betting_certified"])
        self.assertEqual(len(result["games"]), 1)
        self.assertFalse(result["games"][0]["betting_certified"])
        self.assertEqual(result["games"][0]["decision"]["candidates"], [])

    def test_stat_lookahead_rejected(self):
        bundle = example()
        bundle["stats"]["observed_at"] = "2026-10-21T23:05:00Z"
        bundle["sha256"] = _digest(bundle)
        with self.assertRaisesRegex(ValueError, "statistics were observed after"):
            validate(bundle)

    def test_corrupt_import_rejected(self):
        bundle = example()
        bundle["stats"]["season"] = "2025-26"
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            validate(bundle)

    def test_missing_team_submission_blocks_analysis(self):
        bundle = example()
        bundle["injuries"]["team_status"].pop("2026-10-21|Boston Celtics")
        bundle["sha256"] = _digest(bundle)
        output = analyze_offline(bundle)
        self.assertFalse(output["games"])
        self.assertIn("injury", output["failures"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
