import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from nba.close_runtime import capture
from nba.fixture_provider import DeterministicFixtureProvider
from nba.live_runtime import run as live_run
from nba.odds_budget import OddsBudgetExceeded, reserve, status
from nba.providers import OfficialNBAProvider


class OddsBudgetTests(unittest.TestCase):
    def test_daily_budget_resets_and_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"budget.json"
            now=datetime(2026,10,4,1,tzinfo=timezone.utc)
            reserve(path=path,purpose="a",limit=2,now=now)
            second=reserve(path=path,purpose="b",limit=2,now=now)
            self.assertEqual(second["used"],2)
            with self.assertRaises(OddsBudgetExceeded):
                reserve(path=path,purpose="c",limit=2,now=now)
            next_day=status(path=path,limit=2,now=datetime(2026,10,5,1,tzinfo=timezone.utc))
            self.assertEqual(next_day["used"],0)

    def test_close_does_not_call_odds_outside_window(self):
        entry={"entry_key":"e","game_id":"g","commence_time":"2099-01-01T00:00:00Z"}
        with tempfile.TemporaryDirectory() as d:
            paper=Path(d)/"paper.jsonl";paper.write_text(json.dumps(entry)+"\n")
            with patch("nba.close_runtime.fetch_nba_odds") as fetch:
                result=capture(paper_path=str(paper),close_path=str(Path(d)/"close.jsonl"))
            fetch.assert_not_called()
            self.assertEqual(result["odds_api_requests"],0)

    def test_preseason_runtime_never_writes_prospective_ledgers(self):
        fixture=DeterministicFixtureProvider().capture(target_date="2026-11-15")
        from dataclasses import replace
        source=replace(fixture,provider_id="official-nba",role="PROSPECTIVE_SOURCE")
        odds=[{
            "id":"o","home_team":"Boston Celtics","away_team":"New York Knicks",
            "commence_time":"2026-11-15T22:20:00Z","bookmakers":[{
                "key":"pinnacle","last_update":"2026-11-15T21:59:00Z","markets":[
                    {"key":"h2h","outcomes":[{"name":"Boston Celtics","price":1.91},{"name":"New York Knicks","price":1.99}]},
                    {"key":"spreads","outcomes":[{"name":"Boston Celtics","point":-3.5,"price":1.91},{"name":"New York Knicks","point":3.5,"price":1.91}]},
                    {"key":"totals","outcomes":[{"name":"Over","point":226.5,"price":1.91},{"name":"Under","point":226.5,"price":1.91}]}
                ]}]}]
        with tempfile.TemporaryDirectory() as d, patch(
            "nba.live_runtime.OfficialNBAProvider.capture",return_value=source
        ), patch("nba.live_runtime.fetch_nba_odds",return_value=odds), patch(
            "nba.live_runtime.datetime",wraps=datetime
        ) as clock:
            clock.now.return_value=datetime.fromisoformat("2026-11-15T22:00:00+00:00")
            result=live_run(target_date="2026-11-15",output=str(Path(d)/"run.json"),
                snapshot_root=str(Path(d)/"snap"),paper_path=str(Path(d)/"paper.jsonl"),
                forecasts_path=str(Path(d)/"forecast.jsonl"),odds_budget_path=str(Path(d)/"budget.json"),
                operating_mode="preseason")
            self.assertEqual(result["operating_mode"],"preseason")
            self.assertFalse(result["prospective_evidence_eligible"])
            self.assertFalse((Path(d)/"paper.jsonl").exists())
            self.assertFalse((Path(d)/"forecast.jsonl").exists())


if __name__=="__main__":
    unittest.main()
