from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from .nba_stats_api import player_stats, team_stats
from .snapshot_store import canonical_bytes, persist_snapshot
import hashlib
from .team_inputs import build_team_metrics
from .teams import team_info

WINDOWS = (0, 30, 15, 10, 5)


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
        if payload.get("season") != season or payload.get("date_to") != date_to:
            raise RuntimeError("stats cache has mismatched PIT cutoff")
        snapshot = payload.get("snapshot") or {}
        raw = {key: value for key, value in payload.items() if key != "snapshot"}
        if snapshot.get("sha256") != hashlib.sha256(canonical_bytes(raw)).hexdigest():
            raise RuntimeError("stats cache snapshot fingerprint mismatch")
        cached_at = datetime.fromisoformat(str(payload["observed_at"]).replace("Z", "+00:00"))
        evaluated_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if cached_at.tzinfo is None or evaluated_at.tzinfo is None:
            raise RuntimeError("stats cache timestamps require timezone")
        age = (evaluated_at.astimezone(timezone.utc)
               - cached_at.astimezone(timezone.utc)).total_seconds() / 60
        if age < -2:
            raise RuntimeError("stats cache was captured in the future")
        # Refresh an expired cache; never relabel old bytes with a new timestamp.
        if age <= 1440:
            return payload
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
    temporary = cache.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    temporary.replace(cache)
    return payload


def team_metric_from_pack(team: str, pack: dict[str, Any], *, home: bool):
    return build_team_metrics(team, advanced_windows={int(k): v for k, v in pack["advanced_windows"].items()},
                              base_season=pack["base_season"], home=home)


def team_id(team: str) -> int:
    return team_info(team).team_id
