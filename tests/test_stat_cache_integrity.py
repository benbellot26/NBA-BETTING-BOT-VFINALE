import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nba.live_inputs import acquire_stat_pack


DATE="2026-11-15"
SEASON="2026-27"
AT="2026-11-15T20:00:00Z"


def teams():
    return [{"TEAM_NAME":f"Team {index}","OFF_RATING":110.0,
             "DEF_RATING":111.0,"PACE":99.0,"GP":8} for index in range(30)]


def players():
    return [{"PLAYER_ID":index,"TEAM_ID":1610612738,
             "PLAYER_NAME":f"P{index}","MIN":20} for index in range(120)]


def collect(root):
    return acquire_stat_pack(season=SEASON, observed_at=AT, game_date=DATE,
                             snapshot_root=str(root))


class StatCacheIntegrityTests(unittest.TestCase):
    def _capture(self, root):
        with patch("nba.live_inputs.team_stats",return_value=teams()) as team_fetch, patch(
            "nba.live_inputs.player_stats",return_value=players()) as player_fetch:
            pack=collect(root)
            self.assertEqual(team_fetch.call_count,6)
            self.assertEqual(player_fetch.call_count,3)
            return pack

    def test_cache_roundtrip_recovers_integer_window_key_digest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"snap"
            first=self._capture(root)
            with patch("nba.live_inputs.team_stats") as team_fetch, patch(
                "nba.live_inputs.player_stats") as player_fetch:
                second=collect(root)
            self.assertEqual(second["snapshot"]["sha256"],
                             first["snapshot"]["sha256"])
            team_fetch.assert_not_called()
            player_fetch.assert_not_called()

    def test_mutated_model_features_fail_before_model_use(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"snap"
            self._capture(root)
            cache=next((root/"stats_cache").glob("*.json"))
            payload=json.loads(cache.read_text(encoding="utf-8"))
            payload["advanced_windows"]["0"][0]["OFF_RATING"]=999.0
            cache.write_text(json.dumps(payload),encoding="utf-8")
            with patch("nba.live_inputs.team_stats") as upstream:
                with self.assertRaisesRegex(RuntimeError,"digest mismatch"):
                    collect(root)
            upstream.assert_not_called()

    def test_deleted_original_snapshot_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"snap"
            pack=self._capture(root)
            Path(pack["snapshot"]["path"]).unlink()
            with self.assertRaisesRegex(RuntimeError,"original stats snapshot missing"):
                collect(root)

    def test_modified_original_snapshot_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"snap"
            pack=self._capture(root)
            original=Path(pack["snapshot"]["path"])
            original.write_bytes(original.read_bytes()+b" ")
            with self.assertRaisesRegex(RuntimeError,"original stats snapshot digest mismatch"):
                collect(root)

    def test_cache_cannot_redirect_snapshot_outside_root(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"snap"
            self._capture(root)
            cache=next((root/"stats_cache").glob("*.json"))
            payload=json.loads(cache.read_text(encoding="utf-8"))
            payload["snapshot"]["path"]=str(Path(d)/"external.json")
            cache.write_text(json.dumps(payload),encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError,"outside the snapshot root"):
                collect(root)


if __name__=="__main__":
    unittest.main()
