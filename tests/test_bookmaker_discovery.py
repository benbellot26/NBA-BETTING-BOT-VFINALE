import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from nba.bookmaker_discovery import run

def _markets(home="Boston Celtics",away="New York Knicks",quote="2026-10-20T19:59:00Z"):
    return [
        {"key":"h2h","last_update":quote,"outcomes":[
            {"name":home,"price":1.9},{"name":away,"price":2.0}]},
        {"key":"spreads","last_update":quote,"outcomes":[
            {"name":home,"price":1.9,"point":-2.5},
            {"name":away,"price":1.9,"point":2.5}]},
        {"key":"totals","last_update":quote,"outcomes":[
            {"name":"Over","price":1.9,"point":220.5},
            {"name":"Under","price":1.9,"point":220.5}]},
    ]

def fixture():
    all_markets=_markets()
    return {"events":[
        {"id":"e1","home_team":"Boston Celtics","away_team":"New York Knicks",
         "commence_time":"2026-10-20T22:00:00Z","bookmakers":[
             {"key":"book-a","last_update":"2026-10-20T19:59:00Z","markets":all_markets},
             {"key":"book-b","last_update":"2026-10-20T19:59:00Z","markets":all_markets[:2]}]},
        {"id":"e2","home_team":"Boston Celtics","away_team":"New York Knicks",
         "commence_time":"2026-10-21T22:00:00Z","bookmakers":[
             {"key":"book-a","last_update":"2026-10-20T19:59:00Z","markets":all_markets}]}],
        "usage":{"remaining":480,"last_cost":6}}

class BookmakerDiscoveryTests(unittest.TestCase):
    def test_reports_books_without_changing_benchmark(self):
        with tempfile.TemporaryDirectory() as d,patch(
            "nba.bookmaker_discovery.fetch_nba_odds_diagnostic",return_value=fixture()):
            result=run(budget_path=str(Path(d)/"budget.json"))
        self.assertEqual(result["bookmaker_event_counts"]["book-a"],2)
        self.assertEqual(result["complete_featured_market_events"]["book-a"],2)
        self.assertNotIn("book-b",result["complete_featured_market_events"])
        self.assertFalse(result["pinnacle_present"])
        self.assertEqual(result["pinnacle_state"],"ABSENT_FROM_CURRENT_SNAPSHOT")
        self.assertFalse(result["benchmark_changed"])
        self.assertFalse(result["betting_certified"])
        self.assertFalse(result["consensus_replaces_pinnacle"])

    def test_three_books_can_form_consensus_without_changing_benchmark(self):
        markets=_markets()
        raw={"id":"e","home_team":"Boston Celtics","away_team":"New York Knicks",
             "commence_time":"2026-10-20T22:00:00Z","bookmakers":[
                 {"key":"a","last_update":"2026-10-20T19:59:00Z","markets":markets},
                 {"key":"b","last_update":"2026-10-20T19:59:00Z","markets":markets},
                 {"key":"c","last_update":"2026-10-20T19:59:00Z","markets":markets},
             ]}
        with tempfile.TemporaryDirectory() as d,patch(
            "nba.bookmaker_discovery.fetch_nba_odds_diagnostic",
            return_value={"events":[raw],"usage":{}}),patch(
            "nba.bookmaker_discovery.datetime"
        ) as clock:
            from datetime import datetime,timezone
            clock.now.return_value=datetime(2026,10,20,20,0,tzinfo=timezone.utc)
            result=run(budget_path=str(Path(d)/"budget.json"))
        self.assertEqual(result["complete_consensus_events"],1)
        self.assertEqual(result["consensus_market_events"],{"ML":1,"SPREAD":1,"TOTAL":1})
        self.assertFalse(result["consensus_replaces_pinnacle"])

if __name__=="__main__":unittest.main()
