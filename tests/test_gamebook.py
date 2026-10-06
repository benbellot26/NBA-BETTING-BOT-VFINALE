import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch

from nba.gamebook import extract_final_box_text, gamebook_url, parse_final_box_text


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
    def test_pdf_extraction_skips_cover_and_joins_split_final_box(self):
        class Page:
            def __init__(self, layout, plain=None):
                self.layout=layout
                self.plain=plain if plain is not None else layout
            def extract_text(self, extraction_mode=None):
                return self.layout if extraction_mode=="layout" else self.plain

        pages=[
            Page("NBA GAMEBOOK COVER"),
            Page("FINAL BOX\nVISITOR: Los Angeles Lakers\nHOME: Sacramento Kings"),
            Page("SCORE BY PERIOD\n1 2 3 4 FINAL"),
        ]
        fake=SimpleNamespace(PdfReader=lambda _:SimpleNamespace(pages=pages))
        with patch.dict(sys.modules,{"pypdf":fake}):
            text=extract_final_box_text(b"%PDF fixture")
        self.assertNotIn("COVER",text)
        self.assertIn("FINAL BOX",text)
        self.assertIn("VISITOR:",text)
        self.assertIn("HOME:",text)
        self.assertIn("SCORE BY",text)

    def test_pdf_extraction_prefers_plain_text_when_layout_loses_markers(self):
        class Page:
            def extract_text(self, extraction_mode=None):
                if extraction_mode=="layout":
                    return "FINAL BOX"
                return "FINAL BOX\nVISITOR: A\nHOME: B\nSCORE BY PERIOD"

        fake=SimpleNamespace(PdfReader=lambda _:SimpleNamespace(pages=[Page()]))
        with patch.dict(sys.modules,{"pypdf":fake}):
            text=extract_final_box_text(b"%PDF fixture")
        self.assertIn("VISITOR:",text)
        self.assertIn("SCORE BY",text)

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

    def test_final_box_labels_are_optional_when_reconciliation_is_valid(self):
        variant = FINAL_BOX.replace("FINAL BOX\n", "").replace(
            "SCORE BY PERIOD\n1 2 3 4 FINAL\nWarriors 26 24 23 28 101\nPISTONS 21 36 30 28 115\n",
            "",
        )
        result = parse_final_box_text(
            variant,
            expected_away="Golden State Warriors",
            expected_home="Detroit Pistons",
        )
        self.assertEqual(result["away_score"], 101)
        self.assertEqual(result["home_score"], 115)

    def test_team_headers_allow_space_before_colon(self):
        variant = FINAL_BOX.replace("VISITOR:", "VISITOR :").replace(
            "HOME:", "HOME :"
        )
        result = parse_final_box_text(
            variant,
            expected_away="Golden State Warriors",
            expected_home="Detroit Pistons",
        )
        self.assertEqual(result["away_score"], 101)
        self.assertEqual(result["home_score"], 115)

    def test_wrapped_player_rows_are_supported(self):
        wrapped = FINAL_BOX.replace(
            "15 Gui Santos F 29:47 4 10 1 4 4 4 0 5 5 5 3 0 3 0 -3 13",
            "15 Gui Santos F 29:47 4 10 1 4 4 4 0 5\n5 5 3 0 3 0 -3 13",
        ).replace(
            "9 Ausar Thompson F 24:32 4 10 0 1 0 2 0 3 3 4 2 7 5 1 17 8",
            "9 Ausar Thompson F\n24:32 4 10 0 1 0 2 0 3 3 4 2 7 5 1 17 8",
        )
        result = parse_final_box_text(
            wrapped,
            expected_away="Golden State Warriors",
            expected_home="Detroit Pistons",
        )
        self.assertEqual(len(result["away"]["players"]), 11)
        self.assertEqual(len(result["home"]["players"]), 11)
        self.assertEqual(result["away"]["players"][0]["name"], "Gui Santos")
        self.assertEqual(result["home"]["players"][0]["name"], "Ausar Thompson")

    def test_wrapped_team_total_line_is_supported(self):
        wrapped = FINAL_BOX.replace(
            "240:00 35 76 12 33 19 26 10 28 38 23 17 6 25 6 -14 101",
            "240:00 35 76 12 33 19 26\n10 28 38 23 17 6 25 6 -14 101",
        )
        result = parse_final_box_text(
            wrapped,
            expected_away="Golden State Warriors",
            expected_home="Detroit Pistons",
        )
        self.assertEqual(result["away"]["totals"]["FGA"], 76)
        self.assertEqual(result["away_score"], 101)

    def test_overtime_team_minutes_are_supported(self):
        overtime = """
FINAL BOX
VISITOR: Boston Celtics (1-0)
POS MIN FG FGA 3P 3PA FT FTA OR DR TOT A PF ST TO BS +/- PTS
1 Alpha One G 53:00 1 2 0 0 0 0 0 1 1 0 0 0 0 0 0 2
2 Beta Two G 53:00 1 2 0 0 0 0 0 1 1 0 0 0 0 0 0 2
3 Gamma Three F 53:00 1 2 0 0 0 0 0 1 1 0 0 0 0 0 0 2
4 Delta Four F 53:00 1 2 0 0 0 0 0 1 1 0 0 0 0 0 0 2
5 Epsilon Five C 53:00 1 2 0 0 0 0 0 1 1 0 0 0 0 0 0 2
265:00 5 10 0 0 0 0 0 5 5 0 0 0 0 0 0 10
HOME: New York Knicks (0-1)
POS MIN FG FGA 3P 3PA FT FTA OR DR TOT A PF ST TO BS +/- PTS
6 Zeta Six G 53:00 1 2 1 1 0 0 0 1 1 0 0 0 0 0 0 3
7 Eta Seven G 53:00 1 2 1 1 0 0 0 1 1 0 0 0 0 0 0 3
8 Theta Eight F 53:00 1 2 1 1 0 0 0 1 1 0 0 0 0 0 0 3
9 Iota Nine F 53:00 1 2 1 1 0 0 0 1 1 0 0 0 0 0 0 3
10 Kappa Ten C 53:00 1 2 1 1 0 0 0 1 1 0 0 0 0 0 0 3
265:00 5 10 5 5 0 0 0 5 5 0 0 0 0 0 0 15
SCORE BY PERIOD 1 2 3 4 OT FINAL
Celtics 2 2 2 2 2 10
KNICKS 3 3 3 3 3 15
"""
        result = parse_final_box_text(
            overtime,
            expected_away="Boston Celtics",
            expected_home="New York Knicks",
        )
        self.assertEqual(result["away"]["minutes_seconds"], 265 * 60)
        self.assertEqual(result["home"]["minutes_seconds"], 265 * 60)
        self.assertEqual(result["home_score"], 15)

    def test_wrong_schedule_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "team mismatch"):
            parse_final_box_text(
                FINAL_BOX,
                expected_away="Boston Celtics",
                expected_home="Detroit Pistons",
            )


if __name__ == "__main__":
    unittest.main()
