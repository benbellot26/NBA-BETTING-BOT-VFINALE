import unittest

from nba.gamebook import gamebook_url, parse_final_box_text


FINAL_BOX = """
NATIONAL BASKETBALL ASSOCIATION OFFICIAL SCORER'S REPORT
FINAL BOX
VISITOR: GOLDEN STATE WARRIORS (33-37)
POS MIN FG FGA 3P 3PA FT FTA OR DR TOT A PF ST TO BS +/- PTS
15 Gui Santos F 29:47 4 10 1 4 4 4 0 5 5 5 3 0 3 0 -3 13
23 Draymond Green F 22:15 0 2 0 2 0 0 1 4 5 6 2 1 4 1 -15 0
7 Kristaps Porzingis C 10:58 1 5 1 4 2 2 0 3 3 0 1 0 1 2 -6 5
8 De'Anthony Melton G 22:44 5 14 2 6 2 3 1 3 4 0 0 0 4 1 -21 14
2 Brandin Podziemski G 30:25 4 10 2 4 5 6 0 6 6 3 1 1 2 1 -6 15
0 Gary Payton II 24:50 6 8 1 2 1 2 0 3 3 3 2 1 1 0 -3 14
18 LJ Cryer 16:02 3 6 3 5 1 1 0 0 0 1 1 1 2 0 2 10
61 Pat Spencer 22:30 3 6 0 3 0 0 1 3 4 2 0 0 2 1 -8 6
3 Will Richard 28:17 4 5 1 2 2 2 0 1 1 0 3 1 2 0 -4 11
77 Omer Yurtseven 20:58 3 7 0 0 2 6 6 0 6 2 3 1 3 0 2 8
33 Malevy Leons 11:14 2 3 1 1 0 0 1 0 1 1 1 0 1 0 -8 5
240:00 35 76 12 33 19 26 10 28 38 23 17 6 25 6 -14 101
HOME: DETROIT PISTONS (51-19)
POS MIN FG FGA 3P 3PA FT FTA OR DR TOT A PF ST TO BS +/- PTS
9 Ausar Thompson F 24:32 4 10 0 1 0 2 0 3 3 4 2 7 5 1 17 8
12 Tobias Harris F 25:08 6 10 1 1 0 0 1 5 6 5 3 1 1 0 29 13
0 Jalen Duren C 21:26 8 12 0 0 7 9 2 4 6 1 5 1 2 0 14 23
55 Duncan Robinson G 29:04 4 9 2 6 1 2 0 1 1 2 4 2 0 0 37 11
24 Daniss Jenkins G 38:25 7 12 1 3 7 7 2 5 7 8 1 1 3 0 13 22
7 Paul Reed 22:58 6 12 0 3 3 6 3 3 6 3 0 2 0 1 6 15
8 Caris LeVert 21:08 2 9 0 3 1 1 1 1 2 5 2 1 1 1 1 5
5 Ronald Holland II 21:30 5 6 0 1 1 2 0 1 1 0 2 1 1 1 -26 11
31 Javonte Green 20:11 2 3 1 2 0 0 0 3 3 0 0 0 0 0 -14 5
20 Chaz Lanier 12:02 0 2 0 1 0 0 0 0 0 0 0 0 0 0 -1 0
35 Tolu Smith 03:36 1 1 0 0 0 0 0 0 0 1 1 0 0 0 -6 2
240:00 45 86 5 21 20 29 9 26 35 29 20 16 13 4 14 115
SCORE BY PERIOD
1 2 3 4 FINAL
Warriors 26 24 23 28 101
PISTONS 21 36 30 28 115
"""


class GamebookParserTests(unittest.TestCase):
    def test_constructs_official_gamebook_url_from_schedule_identity(self):
        self.assertEqual(
            gamebook_url(
                game_date="2026-03-20",
                away="Golden State Warriors",
                home="Detroit Pistons",
            ),
            "https://statsdmz.nba.com/pdfs/20260320/20260320_GSWDET_book.pdf",
        )

    def test_parses_and_reconciles_final_box(self):
        result = parse_final_box_text(
            FINAL_BOX,
            expected_away="Golden State Warriors",
            expected_home="Detroit Pistons",
        )
        self.assertEqual(result["away_score"], 101)
        self.assertEqual(result["home_score"], 115)
        self.assertEqual(result["away"]["totals"]["FGA"], 76)
        self.assertEqual(result["home"]["totals"]["FGA"], 86)
        self.assertEqual(len(result["away"]["players"]), 11)
        self.assertEqual(len(result["home"]["players"]), 11)
        self.assertEqual(result["away"]["players"][0]["name"], "Gui Santos")
        self.assertEqual(result["home"]["players"][4]["stats"]["AST"], 8)

    def test_wrong_schedule_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "team mismatch"):
            parse_final_box_text(
                FINAL_BOX,
                expected_away="Boston Celtics",
                expected_home="Detroit Pistons",
            )


if __name__ == "__main__":
    unittest.main()
