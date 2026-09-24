import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from nba.close_runtime import capture
from nba.live_runtime import _match
from nba.market_smoke import run as market_smoke
from nba.schedule import ScheduleGame


TIP = "2026-11-15T22:20:00Z"
ENTRY = {
    "entry_key":"g|ML|home_ml","game_id":"g","game_date":"2026-11-15",
    "home":"Boston Celtics","away":"New York Knicks",
    "commence_time":TIP,"entry_at":"2026-11-15T22:00:00Z",
    "market":"ML","selection":"home_ml","price":2.0,"line":None,
    "odds_event_id":"nba-market-test",
}


def odds(quote="2026-11-15T22:18:00Z"):
    return [{
        "id":"nba-market-test","home_team":"Boston Celtics",
        "away_team":"New York Knicks","commence_time":TIP,
        "bookmakers":[{"key":"pinnacle","last_update":quote,"markets":[
            {"key":"h2h","last_update":quote,"outcomes":[
                {"name":"Boston Celtics","price":1.9},
                {"name":"New York Knicks","price":2.0}
            ]},
        ]}],
    }]


def at(hour, minute):
    return datetime(2026,11,15,hour,minute,tzinfo=timezone.utc)


class CloseChronologyTests(unittest.TestCase):
    def _capture(self, directory, response_time, quote):
        paper=Path(directory)/"paper.jsonl"
        paper.write_text(json.dumps(ENTRY)+chr(10),encoding="utf-8")
        close=Path(directory)/"close.jsonl"
        budget=Path(directory)/"budget.json"
        with patch("nba.close_runtime.datetime", wraps=datetime) as clock, patch(
            "nba.close_runtime.fetch_nba_odds",return_value=odds(quote)) as get_odds:
            clock.now.side_effect=[at(22,10),response_time]
            report=capture(paper_path=str(paper),close_path=str(close),
                           odds_budget_path=str(budget))
        get_odds.assert_called_once()
        return report,close,budget

    def test_slow_response_after_tip_is_never_backdated(self):
        with tempfile.TemporaryDirectory() as d:
            report,close,budget=self._capture(d,at(22,21),"2026-11-15T22:19:00Z")
            self.assertEqual(report["added"],0)
            self.assertFalse(close.exists())
            self.assertEqual(report["odds_api_requests"],1)
            self.assertIn("after tip-off",report["failures"][0])
            self.assertEqual(json.loads(budget.read_text())["used"],1)

    def test_quote_timestamp_after_receipt_is_not_a_close(self):
        with tempfile.TemporaryDirectory() as d:
            report,close,_=self._capture(d,at(22,19),"2026-11-15T22:19:30Z")
            self.assertEqual(report["added"],0)
            self.assertFalse(close.exists())
            self.assertIn("outside the entry-to-pre-tip",report["failures"][0])

    def test_pre_tip_response_and_quote_are_stored_with_receipt_time(self):
        with tempfile.TemporaryDirectory() as d:
            report,close,_=self._capture(d,at(22,19),"2026-11-15T22:18:00Z")
            self.assertEqual(report["added"],1,report["failures"])
            row=json.loads(close.read_text().strip())
            self.assertEqual(row["captured_at"],at(22,19).isoformat())

    def test_market_smoke_requires_three_paired_pinnacle_markets_same_event(self):
        partly=odds()[0]
        partly["bookmakers"].append({"key":"other-book","markets":[
            {"key":"spreads","outcomes":[
                {"name":"Boston Celtics","price":1.92,"point":-3.5},
                {"name":"New York Knicks","price":1.92,"point":3.5}]},
            {"key":"totals","outcomes":[
                {"name":"Over","price":1.92,"point":226.5},
                {"name":"Under","price":1.92,"point":226.5}]}
        ]})
        with tempfile.TemporaryDirectory() as d, patch(
            "nba.market_smoke.fetch_nba_odds_diagnostic",
            return_value={"events":[partly],"usage":{"remaining":99}}):
            report=market_smoke(budget_path=str(Path(d)/"budget.json"))
        self.assertEqual(report["pinnacle_events"],1)
        self.assertEqual(report["complete_pinnacle_events"],0)
        self.assertEqual(report["paired_pinnacle_market_events"]["ML"],1)
        self.assertFalse(report["coverage_ready"])

    def test_duplicate_matching_odds_event_is_rejected(self):
        game=ScheduleGame("g","2026-11-15",TIP,"Boston Celtics","New York Knicks",1,"Scheduled")
        event={"home":game.home,"away":game.away,"commence_time":TIP}
        with self.assertRaisesRegex(ValueError,"ambiguous duplicate"):
            _match(game,[event,event.copy()])

    def test_close_match_prefers_provider_event_id_over_shifted_tip(self):
        from nba.close_runtime import _match as close_match
        entry=dict(ENTRY)
        events=[
            {"event_id":"other","home":entry["home"],"away":entry["away"],
             "commence_time":entry["commence_time"],"markets":{}},
            {"event_id":"nba-market-test","home":entry["home"],"away":entry["away"],
             "commence_time":"2026-11-15T22:25:00Z","markets":{}},
        ]
        matched=close_match(entry,events)
        self.assertEqual(matched["event_id"],"nba-market-test")

    def test_close_match_does_not_fallback_when_expected_event_id_disappears(self):
        from nba.close_runtime import _match as close_match
        entry=dict(ENTRY)
        wrong={"event_id":"different","home":entry["home"],"away":entry["away"],
               "commence_time":entry["commence_time"],"markets":{}}
        self.assertIsNone(close_match(entry,[wrong]))


if __name__=="__main__":
    unittest.main()
