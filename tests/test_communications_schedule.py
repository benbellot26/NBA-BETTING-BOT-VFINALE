import unittest
from unittest.mock import patch
from nba.communications_schedule import discover_pdf_url,parse_schedule_text,fetch_reference_schedule

class CommunicationsScheduleTests(unittest.TestCase):
    def test_discovers_official_schedule_pdf(self):
        html='<a href="https://ak-static.cms.nba.com/x/2026-27-NBA-Regular-Season-Schedule-By-Date.pdf">PDF</a>'
        self.assertIn("Schedule-By-Date.pdf",discover_pdf_url(html,"https://pr.nba.com/release"))

    def test_parses_regular_and_neutral_rows(self):
        text="1 Tue. 10/20/26 Boston at Detroit 3:00 PM 3:00 PM NBC/PCK\n189 Sat. 11/7/26 Denver vs Indiana 4:00 PM 5:00 PM B"
        games=parse_schedule_text(text,season="2026-27",minimum_games=2)
        self.assertEqual(games[0].away,"Boston Celtics")
        self.assertEqual(games[0].home,"Detroit Pistons")
        self.assertEqual(games[0].commence_time,"2026-10-20T19:00:00+00:00")
        self.assertTrue(games[1].neutral_site)
        self.assertIsNone(games[1].home)

    def test_fetch_reference_schedule_follows_release_pdf(self):
        html='<a href="/files/2026-27-NBA-Regular-Season-Schedule-By-Date.pdf">PDF</a>'
        rows="\n".join(f"{i+1} Tue. 10/20/26 Boston at Detroit 3:00 PM 3:00 PM" for i in range(1001))
        with patch("nba.communications_schedule.get_text",return_value=html),patch(
            "nba.communications_schedule.get_bytes",return_value=b"pdf"),patch(
            "nba.communications_schedule.extract_pdf_text",return_value=rows):
            games=fetch_reference_schedule(season="2026-27")
        self.assertEqual(len(games),1001)

if __name__=="__main__":unittest.main()
