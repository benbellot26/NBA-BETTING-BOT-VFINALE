import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from nba.bookmaker_discovery import run

def fixture():
    all_markets=[{"key":"h2h","outcomes":[{"name":"A","price":1.9}]},
                 {"key":"spreads","outcomes":[{"name":"A","price":1.9,"point":-2.5}]},
                 {"key":"totals","outcomes":[{"name":"Over","price":1.9,"point":220.5}]}]
    return {"events":[{"bookmakers":[{"key":"book-a","markets":all_markets},{"key":"book-b","markets":all_markets[:2]}]},
                      {"bookmakers":[{"key":"book-a","markets":all_markets}]}],
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
        self.assertFalse(result["benchmark_changed"])
        self.assertFalse(result["betting_certified"])

if __name__=="__main__":unittest.main()
