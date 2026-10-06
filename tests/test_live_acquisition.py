import unittest
from unittest.mock import patch
from nba.injury_pdf import _report_dt, discover_report_links,parse_report_text
from nba.rotation_projection import project_rotation
from nba.schedule import fetch_schedule,parse_schedule,season_for_date
from nba.schedule_context import build_game_context
class LiveAcquisitionTests(unittest.TestCase):
    def test_schedule_parse_and_context(self):
        payload={"leagueSchedule":{"gameDates":[{"gameDate":"10/20/2026 12:00:00 AM","games":[{"gameId":"1","gameDateTimeUTC":"2026-10-20T23:00:00Z","gameStatus":3,"gameStatusText":"Final","homeTeam":{"teamCity":"Boston","teamName":"Celtics","score":"120"},"awayTeam":{"teamCity":"New York","teamName":"Knicks","score":"110"}}]},{"gameDate":"10/21/2026 12:00:00 AM","games":[{"gameId":"2","gameDateTimeUTC":"2026-10-21T23:00:00Z","gameStatus":1,"gameStatusText":"7:00 pm ET","homeTeam":{"teamCity":"Philadelphia","teamName":"76ers"},"awayTeam":{"teamCity":"Boston","teamName":"Celtics"}}]}]}}
        games=parse_schedule(payload);self.assertEqual(games[0].game_date,"2026-10-20");self.assertTrue(games[0].final);ctx=build_game_context(games[1],games,analyzed_at="2026-10-21T12:00:00Z");self.assertTrue(ctx.away_b2b);self.assertGreater(ctx.away_travel_km,0)
    def test_schedule_fetch_falls_back_to_legacy_cdn_route(self):
        payload={"leagueSchedule":{"gameDates":[{"gameDate":"10/06/2026 12:00:00 AM","games":[{"gameId":"0012600010","gameDateTimeUTC":"2026-10-07T02:00:00Z","gameStatus":1,"gameStatusText":"10:00 pm ET","homeTeam":{"teamCity":"Golden State","teamName":"Warriors"},"awayTeam":{"teamCity":"Los Angeles","teamName":"Lakers"}}]}]}}
        with patch("nba.schedule.get_json",side_effect=[RuntimeError("HTTP 403"),payload]) as get_json:
            games=fetch_schedule()
        self.assertEqual(len(games),1)
        self.assertEqual(games[0].game_id,"0012600010")
        self.assertEqual(games[0].home,"Golden State Warriors")
        self.assertEqual(get_json.call_count,2)

    def test_injury_parser(self):
        html='<a href="https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-10-20_05_15PM.pdf">x</a>';self.assertEqual(len(discover_report_links(html,"https://official.nba.com/x")),1);rows=parse_report_text("Boston Celtics\nTatum, Jayson Questionable Injury/Illness - Ankle; Sprain\nBrown, Jaylen Out Injury/Illness - Knee",reported_at="2026-10-20T17:15:00Z");self.assertEqual(len(rows),2);self.assertEqual(rows[1].status,"OUT")
    def test_injury_discovery_finds_escaped_embedded_pdf_url(self):
        html='{"url":"https:\\/\\/ak-static.cms.nba.com\\/referee\\/injury\\/Injury-Report_2026-10-20_05_15PM.pdf"}'
        links=discover_report_links(html,"https://official.nba.com/x")
        self.assertEqual(
            links,
            ["https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-10-20_05_15PM.pdf"],
        )

    def test_injury_timestamp_supports_explicit_and_legacy_half_hour_names(self):
        explicit=_report_dt(
            "https://ak-static.cms.nba.com/referee/injury/"
            "Injury-Report_2026-02-01_11_15PM.pdf"
        )
        legacy=_report_dt(
            "https://ak-static.cms.nba.com/referee/injury/"
            "Injury-Report_2022-02-04_02PM.pdf"
        )
        self.assertEqual((explicit.hour,explicit.minute),(23,15))
        self.assertEqual((legacy.hour,legacy.minute),(14,30))

    def test_rotation_projection(self):
        season=[];recent=[];adv=[]
        for i in range(10):season.append({"TEAM_ID":1610612738,"PLAYER_ID":i,"PLAYER_NAME":f"P{i}","MIN":24});recent.append({"TEAM_ID":1610612738,"PLAYER_ID":i,"PLAYER_NAME":f"P{i}","MIN":24+i/10});adv.append({"TEAM_ID":1610612738,"PLAYER_ID":i,"OFF_RATING":116+i/10,"DEF_RATING":114-i/10,"USG_PCT":.2})
        rows=project_rotation(1610612738,season_base=season,recent_base=recent,season_advanced=adv,injury_status={"P0":"OUT"});self.assertAlmostEqual(sum(x.minutes for x in rows),240,places=2);self.assertEqual(next(x for x in rows if x.name=="P0").status,"OUT")
    def test_season_resolution(self):self.assertEqual(season_for_date("2026-10-20"),"2026-27");self.assertEqual(season_for_date("2027-03-20"),"2026-27")
if __name__=="__main__":unittest.main()
