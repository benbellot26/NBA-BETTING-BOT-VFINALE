from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from .nba_stats_api import player_stats, team_stats
from .snapshot_store import persist_snapshot
from .team_inputs import build_team_metrics
from .teams import team_info

WINDOWS = (0, 30, 15, 10, 5)
CACHE_MAX_AGE_HOURS = 12.0


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("stats cache timestamp requires timezone")
    return parsed.astimezone(timezone.utc)


def _cache_is_fresh(payload: dict[str, Any], *, observed_at: str, season: str,
                    date_to: str, max_age_hours: float = CACHE_MAX_AGE_HOURS) -> bool:
    if payload.get("season") != season or payload.get("date_to") != date_to:
        return False
    try:
        age = (_dt(observed_at) - _dt(str(payload["observed_at"]))).total_seconds() / 3600
    except (KeyError, TypeError, ValueError):
        return False
    return 0 <= age <= max_age_hours


def prior_day_cutoff(game_date: str) -> str:
    """Freeze league statistical inputs at previous calendar day, NBA eastern time."""
    return (date.fromisoformat(game_date) - timedelta(days=1)).strftime("%m/%d/%Y")


def acquire_stat_pack(
    *, season: str, observed_at: str, game_date: str,
    snapshot_root: str = "runtime/snapshots",
) -> dict[str, Any]:
    date_to = prior_day_cutoff(game_date)
    cache = Path(snapshot_root) / "stats_cache" / f"{season}_{date_to.replace('/', '-')}.json"
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
        if _cache_is_fresh(payload, observed_at=observed_at, season=season, date_to=date_to):
            return payload
        # Never relabel an old snapshot with a newer observation time. Refresh
        # from the provider so lineage continues to describe when bytes were seen.
    advanced = {n: team_stats(season=season, last_n_games=n, measure_type="Advanced", date_to=date_to)
                for n in WINDOWS}
    base = team_stats(season=season, measure_type="Base", date_to=date_to)
    player_season = player_stats(season=season, measure_type="Base", date_to=date_to)
    player_recent = player_stats(season=season, last_n_games=10, measure_type="Base", date_to=date_to)
    player_advanced = player_stats(season=season, measure_type="Advanced", date_to=date_to)
    if len(advanced[0]) < 25 or len(base) < 25 or len(player_season) < 100:
        raise RuntimeError("NBA season/team/player stats not yet sufficiently available; no backfill from future")
    payload = {
        "season": season, "date_to": date_to, "observed_at": observed_at,
        "advanced_windows": advanced, "base_season": base,
        "player_season": player_season, "player_recent": player_recent,
        "player_advanced": player_advanced,
    }
    payload["snapshot"] = persist_snapshot(snapshot_root, kind="nba_stats", observed_at=observed_at,
                                            payload=payload, source="stats.nba.com")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return payload


def team_metric_from_pack(team: str, pack: dict[str, Any], *, home: bool):
    return build_team_metrics(team, advanced_windows={int(k): v for k, v in pack["advanced_windows"].items()},
                              base_season=pack["base_season"], home=home)


def team_id(team: str) -> int:
    return team_info(team).team_id
