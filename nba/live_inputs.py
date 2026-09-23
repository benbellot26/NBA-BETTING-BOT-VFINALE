from __future__ import annotations

from typing import Any

from .nba_stats_api import player_stats, team_stats
from .snapshot_store import persist_snapshot
from .team_inputs import build_team_metrics
from .teams import team_info


WINDOWS=(0,30,15,10,5)


def acquire_stat_pack(*, season: str, observed_at: str, snapshot_root: str="runtime/snapshots") -> dict[str,Any]:
    advanced={n:team_stats(season=season,last_n_games=n,measure_type="Advanced") for n in WINDOWS}
    base=team_stats(season=season,last_n_games=0,measure_type="Base")
    player_season=player_stats(season=season,last_n_games=0,measure_type="Base")
    player_recent=player_stats(season=season,last_n_games=10,measure_type="Base")
    player_advanced=player_stats(season=season,last_n_games=0,measure_type="Advanced")
    payload={"season":season,"advanced_windows":advanced,"base_season":base,"player_season":player_season,"player_recent":player_recent,"player_advanced":player_advanced}
    snapshot=persist_snapshot(snapshot_root,kind="nba_stats",observed_at=observed_at,payload=payload,source="stats.nba.com")
    payload["snapshot"]=snapshot
    return payload


def team_metric_from_pack(team: str, pack: dict[str,Any], *, home: bool):
    return build_team_metrics(team,advanced_windows=pack["advanced_windows"],base_season=pack["base_season"],home=home)


def team_id(team: str) -> int:
    return team_info(team).team_id
