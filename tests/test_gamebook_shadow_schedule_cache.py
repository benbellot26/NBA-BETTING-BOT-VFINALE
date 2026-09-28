import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nba.communications_schedule import ReferenceScheduleGame
from nba.gamebook_shadow_runtime import _reference_schedule_cached


def rows():
    game=ReferenceScheduleGame(
        reference_id="r",
        schedule_number=1,
        game_date="2026-11-15",
        commence_time="2026-11-15T22:00:00+00:00",
        team1="New York Knicks",
        team2="Boston Celtics",
        relation="at",
        away="New York Knicks",
        home="Boston Celtics",
        neutral_site=False,
    )
    return [game for _ in range(1000)]


class GamebookShadowScheduleCacheTests(unittest.TestCase):
    def test_fresh_cache_avoids_repeated_schedule_fetch(self):
        now=dt.datetime(2026,11,15,12,tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as d, patch(
            "nba.gamebook_shadow_runtime.fetch_reference_schedule",
            return_value=rows(),
        ) as fetch:
            path=Path(d)/"schedule.json"
            first=_reference_schedule_cached(
                season="2026-27",now=now,cache_path=path)
            second=_reference_schedule_cached(
                season="2026-27",
                now=now+dt.timedelta(hours=1),
                cache_path=path,
            )
            self.assertEqual(len(first),1000)
            self.assertEqual(len(second),1000)
            self.assertEqual(fetch.call_count,1)

    def test_stale_cache_refreshes(self):
        now=dt.datetime(2026,11,15,12,tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as d, patch(
            "nba.gamebook_shadow_runtime.fetch_reference_schedule",
            return_value=rows(),
        ) as fetch:
            path=Path(d)/"schedule.json"
            _reference_schedule_cached(
                season="2026-27",now=now,cache_path=path)
            _reference_schedule_cached(
                season="2026-27",
                now=now+dt.timedelta(hours=25),
                cache_path=path,
            )
            self.assertEqual(fetch.call_count,2)


if __name__=="__main__":
    unittest.main()
