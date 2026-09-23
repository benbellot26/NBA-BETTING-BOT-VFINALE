from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any

from .nba_stats_api import player_stats, team_stats
from .snapshot_store import canonical_bytes, persist_snapshot
from .team_inputs import build_team_metrics
from .teams import team_info

WINDOWS = (0, 30, 15, 10, 5)


def prior_day_cutoff(game_date: str) -> str:
    """Freeze league statistical inputs at previous calendar day, NBA eastern time."""
    return (date.fromisoformat(game_date) - timedelta(days=1)).strftime("%m/%d/%Y")


def _verify_stats_cache(*, payload: dict[str, Any], season: str, date_to: str,
                        snapshot_root: str) -> dict[str, Any]:
    """Bind cached model features to the original locally persisted snapshot.

    A SHA proves consistency of stored bytes, NOT authenticity of NBA.com
    collection time or provenance. Never repair a corrupt cache silently.
    """
    if payload.get("season") != season or payload.get("date_to") != date_to:
        raise RuntimeError("stats cache has mismatched PIT cutoff")
    meta = payload.get("snapshot")
    if not isinstance(meta, dict) or meta.get("kind") != "nba_stats" or (
        meta.get("source") != "stats.nba.com"
    ) or meta.get("observed_at") != payload.get("observed_at"):
        raise RuntimeError("stats cache has inconsistent snapshot metadata")
    try:
        windows = payload["advanced_windows"]
        if not isinstance(windows, dict):
            raise ValueError("missing advanced windows")
        # The original snapshot was serialized with integer window keys.
        # JSON cache loads them as strings; normalize before recomputing its
        # canonical SHA to avoid a false mismatch from key sort order.
        normalized = {int(key): rows for key, rows in windows.items()}
        if len(normalized) != len(windows) or set(normalized) != set(WINDOWS):
            raise ValueError("invalid advanced windows")
        content = {key: value for key, value in payload.items()
                   if key != "snapshot"}
        content["advanced_windows"] = normalized
        data = canonical_bytes(content)
        digest = hashlib.sha256(data).hexdigest()
        if meta.get("sha256") != digest or meta.get("bytes") != len(data):
            raise RuntimeError("stats cache digest mismatch")
        source = Path(str(meta["path"])).resolve()
        allowed = (Path(snapshot_root).resolve() / "nba_stats").resolve()
        if not source.is_relative_to(allowed):
            raise RuntimeError("stats cache snapshot path is outside the snapshot root")
        if not source.is_file():
            raise RuntimeError("original stats snapshot missing")
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise RuntimeError("original stats snapshot digest mismatch")
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise RuntimeError(f"stats cache integrity check failed: {type(exc).__name__}") from None
    return payload


def acquire_stat_pack(
    *, season: str, observed_at: str, game_date: str,
    snapshot_root: str = "runtime/snapshots",
) -> dict[str, Any]:
    date_to = prior_day_cutoff(game_date)
    cache = Path(snapshot_root) / "stats_cache" / f"{season}_{date_to.replace('/', '-')}.json"
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
        return _verify_stats_cache(
            payload=payload, season=season, date_to=date_to,
            snapshot_root=snapshot_root,
        )
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
