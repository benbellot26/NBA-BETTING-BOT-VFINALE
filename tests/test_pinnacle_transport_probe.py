import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nba.pinnacle_transport_probe import run


def _markets(home="Boston Celtics", away="New York Knicks"):
    return [
        {"key":"h2h","last_update":"2026-10-04T19:59:00Z","outcomes":[
            {"name":home,"price":1.9},{"name":away,"price":2.0}]},
        {"key":"spreads","last_update":"2026-10-04T19:59:00Z","outcomes":[
            {"name":home,"price":1.9,"point":-2.5},
            {"name":away,"price":1.9,"point":2.5}]},
        {"key":"totals","last_update":"2026-10-04T19:59:00Z","outcomes":[
            {"name":"Over","price":1.9,"point":220.5},
            {"name":"Under","price":1.9,"point":220.5}]},
    ]


def _event(bookmakers):
    return {
        "id":"e1",
        "home_team":"Boston Celtics",
        "away_team":"New York Knicks",
        "commence_time":"2026-10-04T22:00:00Z",
        "bookmakers":bookmakers,
    }


class PinnacleTransportProbeTests(unittest.TestCase):
    def test_targeted_empty_but_eu_has_pinnacle_is_filter_mismatch(self):
        targeted={"events":[_event([])],"usage":{}}
        regional={"events":[_event([
            {"key":"pinnacle","last_update":"2026-10-04T19:59:00Z","markets":_markets()}
        ])],"usage":{}}
        with tempfile.TemporaryDirectory() as d, patch(
            "nba.pinnacle_transport_probe.fetch_nba_odds_diagnostic",
            side_effect=[targeted, regional],
        ), patch("nba.pinnacle_transport_probe.datetime") as clock:
            from datetime import datetime, timezone
            clock.now.return_value=datetime(2026,10,4,20,0,tzinfo=timezone.utc)
            result=run(budget_path=str(Path(d)/"budget.json"))
        self.assertEqual(result["state"],"TARGET_FILTER_MISMATCH")
        self.assertEqual(result["request_count"],2)
        self.assertFalse(result["pinnacle_replacement_allowed"])
        self.assertFalse(result["production_market_authorized"])

    def test_targeted_complete_is_ready_diagnostic_only(self):
        event=_event([
            {"key":"pinnacle","last_update":"2026-10-04T19:59:00Z","markets":_markets()}
        ])
        payload={"events":[event],"usage":{}}
        with tempfile.TemporaryDirectory() as d, patch(
            "nba.pinnacle_transport_probe.fetch_nba_odds_diagnostic",
            side_effect=[payload,payload],
        ), patch("nba.pinnacle_transport_probe.datetime") as clock:
            from datetime import datetime, timezone
            clock.now.return_value=datetime(2026,10,4,20,0,tzinfo=timezone.utc)
            result=run(
                sport_key="basketball_nba_preseason",
                budget_path=str(Path(d)/"budget.json"),
            )
        self.assertEqual(result["state"],"TARGETED_PINNACLE_READY")
        self.assertEqual(result["season_mode"],"PRESEASON")
        self.assertEqual(result["targeted"]["complete_pinnacle_events"],1)
        self.assertFalse(result["betting_certified"])

    def test_events_without_pinnacle_are_classified(self):
        event=_event([
            {"key":"betmgm","last_update":"2026-10-04T19:59:00Z","markets":_markets()}
        ])
        targeted={"events":[_event([])],"usage":{}}
        regional={"events":[event],"usage":{}}
        with tempfile.TemporaryDirectory() as d, patch(
            "nba.pinnacle_transport_probe.fetch_nba_odds_diagnostic",
            side_effect=[targeted,regional],
        ):
            result=run(budget_path=str(Path(d)/"budget.json"))
        self.assertEqual(result["state"],"PINNACLE_NOT_CURRENTLY_LISTED")


if __name__=="__main__":
    unittest.main()
