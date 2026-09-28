import json
import tempfile
import unittest
from pathlib import Path

from nba.market_availability import record


class MarketAvailabilityTests(unittest.TestCase):
    def test_persists_targeted_empty_history_without_replacing_pinnacle(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            market=root/"market.json"
            discovery=root/"discovery.json"
            history=root/"history.jsonl"
            summary=root/"summary.json"
            market.write_text(json.dumps({
                "schema":"pulsar-nba-market-smoke-v2",
                "checked_at":"2026-10-01T12:00:00+00:00",
                "availability_state":"PINNACLE_TARGET_EMPTY",
                "events":10,
                "pinnacle_events":0,
                "complete_pinnacle_events":0,
                "raw_events_with_any_bookmaker":0,
                "raw_events_with_pinnacle":0,
            }),encoding="utf-8")
            discovery.write_text(json.dumps({
                "checked_at":"2026-10-01T11:00:00+00:00",
                "events":10,
                "pinnacle_present":False,
                "pinnacle_state":"ABSENT_FROM_CURRENT_SNAPSHOT",
            }),encoding="utf-8")
            first=record(
                market_path=str(market),discovery_path=str(discovery),
                history_path=str(history),summary_path=str(summary))
            second=record(
                market_path=str(market),discovery_path=str(discovery),
                history_path=str(history),summary_path=str(summary))
            self.assertEqual(first["observations"],1)
            self.assertEqual(second["observations"],1)
            self.assertEqual(first["consecutive_not_ready"],1)
            self.assertFalse(first["replacement_allowed"])
            self.assertEqual(
                len([x for x in history.read_text().splitlines() if x.strip()]),1)

    def test_ready_snapshot_breaks_absence_streak(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);history=root/"history.jsonl"
            history.write_text(
                json.dumps({"entry_key":"a","availability_state":"PINNACLE_TARGET_EMPTY"})+"\n",
                encoding="utf-8")
            market=root/"market.json"
            market.write_text(json.dumps({
                "schema":"pulsar-nba-market-smoke-v2",
                "checked_at":"2026-10-02T12:00:00+00:00",
                "availability_state":"PINNACLE_READY",
                "events":10,"pinnacle_events":10,"complete_pinnacle_events":10,
                "raw_events_with_any_bookmaker":10,"raw_events_with_pinnacle":10,
            }),encoding="utf-8")
            result=record(
                market_path=str(market),
                discovery_path=str(root/"missing.json"),
                history_path=str(history),summary_path=str(root/"summary.json"))
            self.assertEqual(result["consecutive_not_ready"],0)
            self.assertEqual(result["latest_state"],"PINNACLE_READY")


if __name__=="__main__":
    unittest.main()
