import unittest
from unittest.mock import patch

from nba.injury_pdf import (
    discover_injury_page_url,
    injury_page_url,
    latest_report_url,
)
from nba.provider_smoke import _classify_failure


class InjuryDiscoveryTests(unittest.TestCase):
    def test_canonical_page_is_preferred_when_reachable(self):
        canonical = injury_page_url("2025-26")
        with patch("nba.injury_pdf.get_text", return_value="<html></html>") as text, patch(
            "nba.injury_pdf.get_json"
        ) as search:
            result = discover_injury_page_url(season="2025-26")
        self.assertEqual(result, canonical)
        text.assert_called_once()
        search.assert_not_called()

    def test_official_search_recovers_exact_season_page(self):
        expected = "https://official.nba.com/nba-injury-report-2025-26-season/"
        rows = [{
            "id": 16977,
            "title": "NBA Injury Report: 2025-26 Season",
            "url": expected,
            "subtype": "post",
        }]
        with patch("nba.injury_pdf.get_text", side_effect=RuntimeError("HTTP 404")), patch(
            "nba.injury_pdf.get_json", return_value=rows
        ):
            self.assertEqual(
                discover_injury_page_url(season="2025-26"),
                expected,
            )

    def test_search_never_falls_back_to_another_season(self):
        rows = [{
            "title": "NBA Injury Report: 2025-26 Season",
            "url": "https://official.nba.com/nba-injury-report-2025-26-season/",
        }]
        with patch("nba.injury_pdf.get_text", side_effect=RuntimeError("HTTP 404")), patch(
            "nba.injury_pdf.get_json", return_value=rows
        ):
            with self.assertRaisesRegex(RuntimeError, "not published for season 2026-27"):
                discover_injury_page_url(season="2026-27")

    def test_search_rejects_non_official_domain(self):
        rows = [{
            "title": "NBA Injury Report: 2026-27 Season",
            "url": "https://example.com/nba-injury-report-2026-27-season/",
        }]
        with patch("nba.injury_pdf.get_text", side_effect=RuntimeError("HTTP 404")), patch(
            "nba.injury_pdf.get_json", return_value=rows
        ):
            with self.assertRaisesRegex(RuntimeError, "not published"):
                discover_injury_page_url(season="2026-27")

    def test_ambiguous_exact_search_results_fail_closed(self):
        rows = [
            {
                "title": "NBA Injury Report: 2025-26 Season",
                "url": "https://official.nba.com/nba-injury-report-2025-26-season/",
            },
            {
                "title": "NBA Injury Report: 2025-26 Season",
                "url": "https://official.nba.com/alternate-2025-26-injury-report/",
            },
        ]
        with patch("nba.injury_pdf.get_text", side_effect=RuntimeError("HTTP 404")), patch(
            "nba.injury_pdf.get_json", return_value=rows
        ):
            with self.assertRaisesRegex(RuntimeError, "ambiguous"):
                discover_injury_page_url(season="2025-26")

    def test_latest_report_selects_latest_timestamped_pdf(self):
        page = "https://official.nba.com/nba-injury-report-2025-26-season/"
        html = """
        <a href="/wp-content/uploads/Injury-Report_2026-04-01_05_30PM.pdf">old</a>
        <a href="/wp-content/uploads/Injury-Report_2026-04-01_08_30PM.pdf">new</a>
        """
        with patch("nba.injury_pdf.discover_injury_page_url", return_value=page), patch(
            "nba.injury_pdf.get_text", return_value=html
        ):
            result = latest_report_url(season="2025-26")
        self.assertIn("08_30PM.pdf", result)

    def test_explicit_page_override_must_remain_official(self):
        with self.assertRaisesRegex(ValueError, "official.nba.com"):
            latest_report_url(
                season="2025-26",
                page_url="https://example.com/injuries/",
            )

    def test_not_published_discovery_is_classified_correctly(self):
        exc = RuntimeError(
            "official NBA injury report is not published for season 2026-27"
        )
        self.assertEqual(
            _classify_failure(exc, source="injuries"),
            "NOT_PUBLISHED",
        )


if __name__ == "__main__":
    unittest.main()
