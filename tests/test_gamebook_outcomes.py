import json
import tempfile
import unittest
from pathlib import Path

from nba.gamebook import parse_final_box_text
from nba.gamebook_outcomes import (
    SOURCE,
    cached_gamebook_finals,
    is_gamebook_final,
)
from nba.gamebook_stats import _json_sha256
from nba.performance_runtime import _final_for_record
from nba.providers import OfficialGamebookOutcomeProvider, OfficialOutcomeProvider
from test_gamebook import FINAL_BOX


class GamebookOutcomeTests(unittest.TestCase):
    def _cache(self, root: Path):
        parsed = parse_final_box_text(
            FINAL_BOX,
            expected_away="Golden State Warriors",
            expected_home="Detroit Pistons",
        )
        payload = {
            "schema": "pulsar-nba-gamebook-cache-v1",
            "source": "NBA_OFFICIAL_SCORERS_REPORT",
            "role": "ALTERNATE_REFERENCE_ONLY",
            "reference_id": "nba-pr-2025-26-2026-03-20-1",
            "game_date": "2026-03-20",
            "away": "Golden State Warriors",
            "home": "Detroit Pistons",
            "pdf_sha256": "a" * 64,
            "parsed_sha256": _json_sha256(parsed),
            "parsed": parsed,
        }
        path = root / "gamebooks"
        path.mkdir(parents=True)
        (path / "g.json").write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def test_cached_official_gamebook_becomes_final_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            payload = self._cache(root)
            finals = cached_gamebook_finals(root)
        game = finals[payload["reference_id"]]
        self.assertTrue(game.final)
        self.assertTrue(is_gamebook_final(game))
        self.assertEqual(game.home_score, payload["parsed"]["home_score"])
        self.assertEqual(game.away_score, payload["parsed"]["away_score"])
        self.assertEqual(game.commence_time, "")

    def test_schedule_failure_falls_back_to_validated_gamebook_cache(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            payload = self._cache(root)
            fallback = OfficialGamebookOutcomeProvider(cache_root=str(root))
            provider = OfficialOutcomeProvider(
                fetcher=lambda: (_ for _ in ()).throw(RuntimeError("HTTP 403")),
                fallback=fallback,
            )
            finals = provider.finals()
        self.assertIn(payload["reference_id"], finals)

    def test_noncommunications_forecast_can_match_unique_gamebook_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._cache(root)
            finals = OfficialGamebookOutcomeProvider(
                cache_root=str(root)
            ).finals()
        record = {
            "game_id": "0022509999",
            "game_date": "2026-03-20",
            "home": "Detroit Pistons",
            "away": "Golden State Warriors",
        }
        matched = _final_for_record(record, finals)
        self.assertIsNotNone(matched)
        self.assertTrue(is_gamebook_final(matched))

    def test_tampered_cached_gamebook_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            payload = self._cache(root)
            path = root / "gamebooks" / "g.json"
            payload["parsed"]["home_score"] += 1
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "invalid cached official gamebook"):
                cached_gamebook_finals(root)


if __name__ == "__main__":
    unittest.main()
