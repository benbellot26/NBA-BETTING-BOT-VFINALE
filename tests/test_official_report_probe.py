import unittest
from unittest.mock import MagicMock, patch

from nba.official_report_probe import (
    _gamebook_probe,
    _injury_page_probe,
    _media_probe,
    run,
)


class OfficialReportProbeTests(unittest.TestCase):
    def test_gamebook_structure_requires_official_final_box_and_team_totals(self):
        text = """
NATIONAL BASKETBALL ASSOCIATION OFFICIAL SCORER'S REPORT
FINAL BOX
VISITOR: Golden State Warriors
POS MIN FG FGA 3P 3PA FT FTA OR DR TOT A PF ST TO BS +/- PTS
240:00 35 76 12 33 19 26 10 28 38 23 17 6 25 6 -14 101
HOME: DETROIT PISTONS
POS MIN FG FGA 3P 3PA FT FTA OR DR TOT A PF ST TO BS +/- PTS
240:00 45 86 5 21 20 29 9 26 35 29 20 16 13 4 14 115
SCORE BY PERIOD
Warriors 26 24 23 28 101
PISTONS 21 36 30 28 115
"""
        page = MagicMock()
        page.extract_text.return_value = text
        reader = MagicMock()
        reader.pages = [page, page]
        expected = {
            "away": "Golden State Warriors", "home": "Detroit Pistons",
            "away_score": 101, "home_score": 115,
            "away_fga": 76, "home_fga": 86,
        }
        parsed = {
            "away_score": 101, "home_score": 115,
            "away": {"totals": {"FGA": 76}, "players": [{}] * 11},
            "home": {"totals": {"FGA": 86}, "players": [{}] * 11},
        }
        with patch("pypdf.PdfReader", return_value=reader), patch(
            "nba.official_report_probe.parse_gamebook_pdf", return_value=parsed
        ):
            result = _gamebook_probe(b"%PDF-fake", expected)
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["team_total_line_count"], 2)
        self.assertFalse(result["raw_text_persisted"])
        self.assertEqual(len(result["sha256"]), 64)

    def test_media_probe_persists_only_structure(self):
        html = (
            '<html><a href="/stats/gamebooks">Gamebooks</a>'
            '<h1>Media Central Game Stats</h1>'
            '<p>Provided by Elias</p><p>Overall Statistics</p></html>'
        )
        result = _media_probe(html)
        self.assertTrue(result["ok"])
        self.assertFalse(result["raw_html_persisted"])
        self.assertIn("/stats/gamebooks", result["report_link_hints"])
        self.assertNotIn("html", result)

    def test_injury_page_probe_persists_safe_structure_only(self):
        html = (
            '<script id="loader" src="/wp-content/injury-loader.js"></script>'
            '<div data-endpoint="https://official.nba.com/wp-json/injury/v1/reports?nonce=secret"></div>'
            '<script>{"pdf":"https:\\/\\/ak-static.cms.nba.com\\/referee\\/injury\\/'
            'Injury-Report_2026-02-01_11_15PM.pdf"}</script>'
        )
        result = _injury_page_probe(html, season="2025-26")
        self.assertTrue(result["ok"])
        self.assertFalse(result["raw_html_persisted"])
        self.assertGreater(result["marker_counts"]["Injury-Report_"], 0)
        self.assertIn(
            "https://ak-static.cms.nba.com/referee/injury/"
            "Injury-Report_2026-02-01_11_15PM.pdf",
            result["safe_endpoint_hints"],
        )
        self.assertTrue(
            all("?" not in url for url in result["safe_endpoint_hints"])
        )
        self.assertNotIn("nonce=secret", str(result))

    def test_network_failure_is_diagnostic_only(self):
        with patch(
            "nba.official_report_probe.get_bytes",
            side_effect=RuntimeError("blocked"),
        ), patch(
            "nba.official_report_probe.get_text",
            side_effect=RuntimeError("blocked"),
        ):
            result = run()
        self.assertEqual(result["role"], "NETWORK_DIAGNOSTIC_ONLY")
        self.assertFalse(result["predictive_evidence_eligible"])
        self.assertFalse(result["production_provider_authorized"])
        self.assertFalse(result["official_gamebook_candidate"])
        self.assertEqual(result["odds_api_requests"], 0)


if __name__ == "__main__":
    unittest.main()
