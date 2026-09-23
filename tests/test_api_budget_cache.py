import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from nba.close_runtime import capture
from nba.live_inputs import acquire_stat_pack
from nba.snapshot_store import persist_snapshot


class OddsCreditProtectionTests(unittest.TestCase):
    def _paper(self, directory, offset_minutes):
        tip = (datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)).isoformat()
        path = Path(directory) / "paper.jsonl"
        path.write_text(json.dumps({
            "entry_key": "x", "commence_time": tip, "game_id": "g",
            "entry_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            "market": "ML", "selection": "home_ml", "price": 2.0,
            "home": "Boston Celtics", "away": "New York Knicks",
        }) + "\n")
        return path

    def test_no_paid_close_request_outside_window(self):
        with tempfile.TemporaryDirectory() as root:
            paper = self._paper(root, 70)
            with patch("nba.close_runtime.fetch_nba_odds") as api:
                result = capture(paper_path=str(paper),
                                 close_path=str(Path(root) / "close.jsonl"))
            api.assert_not_called()
            self.assertEqual(result["odds_requests"], 0)
            self.assertEqual(result["eligible_now"], 0)

    def test_no_paid_request_after_tip(self):
        with tempfile.TemporaryDirectory() as root:
            paper = self._paper(root, -5)
            with patch("nba.close_runtime.fetch_nba_odds") as api:
                result = capture(paper_path=str(paper),
                                 close_path=str(Path(root) / "close.jsonl"))
            api.assert_not_called()
            self.assertEqual(result["odds_requests"], 0)

    def test_eligible_close_can_make_one_request(self):
        with tempfile.TemporaryDirectory() as root:
            paper = self._paper(root, 10)
            with patch("nba.close_runtime.fetch_nba_odds", return_value=[]) as api:
                result = capture(paper_path=str(paper),
                                 close_path=str(Path(root) / "close.jsonl"))
            api.assert_called_once()
            self.assertEqual(result["odds_requests"], 1)


class CachePointInTimeTests(unittest.TestCase):
    @staticmethod
    def _cache(root, *, now, age_minutes):
        source = (now - timedelta(minutes=age_minutes)).isoformat()
        date_to = "11/14/2026"
        directory = Path(root) / "stats_cache"
        directory.mkdir(parents=True)
        cache = directory / "2026-27_11-14-2026.json"
        payload = {
            "season": "2026-27", "date_to": date_to,
            "observed_at": source, "advanced_windows": {},
            "base_season": [], "player_season": [],
            "player_recent": [], "player_advanced": [],
        }
        payload["snapshot"] = persist_snapshot(
            root, kind="nba_stats", observed_at=source,
            payload=payload, source="stats.nba.com")
        cache.write_text(json.dumps(payload), encoding="utf-8")
        return cache

    def test_fresh_snapshot_reused_without_provider_request(self):
        with tempfile.TemporaryDirectory() as root:
            now = datetime(2026, 11, 15, 22, tzinfo=timezone.utc)
            self._cache(root, now=now, age_minutes=10)
            with patch("nba.live_inputs.team_stats") as api:
                row = acquire_stat_pack(season="2026-27", observed_at=now.isoformat(),
                                        game_date="2026-11-15", snapshot_root=root)
            api.assert_not_called()
            self.assertLess((now - datetime.fromisoformat(row["observed_at"])).total_seconds(), 1440)

    def test_expired_snapshot_is_refetched_or_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            now = datetime(2026, 11, 15, 22, tzinfo=timezone.utc)
            self._cache(root, now=now, age_minutes=2000)
            with patch("nba.live_inputs.team_stats", side_effect=RuntimeError("offline")) as api:
                with self.assertRaisesRegex(RuntimeError, "offline"):
                    acquire_stat_pack(season="2026-27", observed_at=now.isoformat(),
                                      game_date="2026-11-15", snapshot_root=root)
            api.assert_called_once()

    def test_tampered_cache_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            now = datetime(2026, 11, 15, 22, tzinfo=timezone.utc)
            cache = self._cache(root, now=now, age_minutes=10)
            row = json.loads(cache.read_text())
            row["player_season"].append({"player": "fabricated"})
            cache.write_text(json.dumps(row))
            with self.assertRaisesRegex(RuntimeError, "fingerprint mismatch"):
                acquire_stat_pack(season="2026-27", observed_at=now.isoformat(),
                                  game_date="2026-11-15", snapshot_root=root)


if __name__ == "__main__":
    unittest.main()
