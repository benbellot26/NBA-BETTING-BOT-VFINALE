import unittest

from nba.reference_schedule import parse_scoreboard


class ReferenceScheduleTests(unittest.TestCase):
    def test_parses_only_identity_time_and_teams(self):
        payload={
            "events":[{
                "id":"401999999",
                "date":"2026-10-07T02:00:00Z",
                "competitions":[{
                    "id":"401999999",
                    "competitors":[
                        {
                            "homeAway":"home",
                            "team":{"displayName":"Golden State Warriors"},
                            "score":"0",
                        },
                        {
                            "homeAway":"away",
                            "team":{"displayName":"Los Angeles Lakers"},
                            "score":"0",
                        },
                    ],
                }],
            }]
        }
        rows=parse_scoreboard(payload)
        self.assertEqual(len(rows),1)
        game=rows[0]
        self.assertEqual(game.reference_id,"espn-401999999")
        self.assertEqual(game.game_date,"2026-10-06")
        self.assertEqual(game.commence_time,"2026-10-07T02:00:00+00:00")
        self.assertEqual(game.away,"Los Angeles Lakers")
        self.assertEqual(game.home,"Golden State Warriors")
        self.assertEqual(game.relation,"at")
        self.assertFalse(game.neutral_site)


if __name__=="__main__":
    unittest.main()
