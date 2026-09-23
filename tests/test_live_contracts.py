import unittest
from unittest.mock import patch

from nba.injury_pdf import parse_report_document, game_report_ready, _report_dt
from nba.market import best_execution, pinnacle_no_vig, fresh_quote
from nba.odds_normalizer import normalize_game
from nba.provider_http import get_bytes, ProviderError
from nba.rotation_projection import normalized_player_name, project_rotation


class LiveContractsTests(unittest.TestCase):
    def test_spread_pair_requires_opposite_handicap(self):
        book = [{"bookmaker": "pinnacle", "last_update": "2026-10-21T22:00:00Z",
                 "selections": [{"selection": "HOME", "point": -4.5, "price": 1.96},
                                {"selection": "AWAY", "point": 4.5, "price": 1.90},
                                {"selection": "AWAY", "point": 3.5, "price": 1.95}]}]
        fair = pinnacle_no_vig(book, "HOME", "AWAY", point=-4.5)
        self.assertIsNotNone(fair)
        self.assertAlmostEqual(fair["HOME"] + fair["AWAY"], 1.0)
        self.assertIsNone(pinnacle_no_vig(book, "HOME", "AWAY", point=-3.5))
        self.assertIsNone(best_execution(book, "HOME", point=0.0))

    def test_totals_require_identical_number(self):
        books = [{"bookmaker": "pinnacle", "selections": [
            {"selection": "OVER", "point": 224.5, "price": 1.92},
            {"selection": "UNDER", "point": 225.5, "price": 1.90}]}]
        self.assertIsNone(pinnacle_no_vig(books, "OVER", "UNDER", point=224.5))

    def test_injury_pdf_date_team_and_player(self):
        pdf_text = ("Injury Report: 03/04/26 05:15 AM\n"
                    "03/04/2026 07:30 (ET) CHA@BOS Charlotte Hornets NOT YET SUBMITTED\n"
                    "Boston Celtics Tatum, Jayson Out Injury/Illness - Right Achilles\n"
                    "UTA@PHI Utah Jazz Jackson Jr., Jaren Out Injury/Illness - Knee\n"
                    "Kessler, Walker Questionable Injury/Illness - Shoulder\n"
                    "03/05/2026 DAL@ORL Dallas Mavericks NOT YET SUBMITTED\n")
        parsed = parse_report_document(pdf_text, reported_at="2026-03-04T10:15:00+00:00")
        self.assertEqual(parsed["records"][0]["player_name"], "Jayson Tatum")
        self.assertEqual(parsed["records"][1]["player_name"], "Jaren Jackson Jr.")
        self.assertEqual(parsed["records"][2]["game_date"], "2026-03-04")
        self.assertFalse(game_report_ready(parsed, game_date="2026-03-04",
                                           home="Boston Celtics", away="Charlotte Hornets"))
        self.assertEqual(parsed["team_status"]["2026-03-05|Dallas Mavericks"], "NOT_YET_SUBMITTED")

    def test_et_timezone_is_not_utc(self):
        d = _report_dt("Injury-Report_2026-03-04_05_15AM.pdf")
        self.assertEqual(d.utcoffset().total_seconds(), -5 * 3600)

    def test_player_matching_accent_and_order(self):
        self.assertEqual(normalized_player_name("Luka Dončić"), normalized_player_name("Luka Doncic"))
        self.assertEqual(normalized_player_name("Jaren Jackson Jr."), normalized_player_name("Jaren Jackson Jr."))

    def test_timestamp_requires_fresh_quote(self):
        self.assertTrue(fresh_quote("2026-10-20T21:50:00Z", "2026-10-20T22:00:00Z"))
        self.assertFalse(fresh_quote(None, "2026-10-20T22:00:00Z"))
        self.assertFalse(fresh_quote("2026-10-20T21:30:00Z", "2026-10-20T22:00:00Z"))

    def test_provider_errors_never_expose_secret(self):
        with patch("nba.provider_http.urlopen", side_effect=OSError("failed for apiKey=SUPERSECRET")):
            with self.assertRaises(ProviderError) as caught:
                get_bytes("https://example.com/sports?apiKey=SUPERSECRET", retries=0)
        self.assertNotIn("SUPERSECRET", str(caught.exception))

    def test_normalizer_canonicalizes_clippers(self):
        event = normalize_game({"id": "g", "home_team": "Los Angeles Clippers",
                                "away_team": "Boston Celtics", "bookmakers": [{
                                    "key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
                                        {"name": "Los Angeles Clippers", "price": 1.9},
                                        {"name": "Boston Celtics", "price": 2.0}]}]}]})
        self.assertEqual(event["home"], "LA Clippers")
        self.assertEqual(len(event["markets"]["ML"][0]["selections"]), 2)


if __name__ == "__main__":
    unittest.main()
