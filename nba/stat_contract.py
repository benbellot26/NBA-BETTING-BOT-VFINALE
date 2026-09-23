"""Fail-closed contract for normalized NBA team and player statistical inputs.

The league prior is a model coefficient, NOT a substitute for missing live
provider fields. No betting decision or prospectively certified observation
may be built on a silently incomplete score/pace/rotation input.
"""
from __future__ import annotations

import math
from typing import Any

from .teams import canonical_team, team_info

ADVANCED_LIMITS = {
    "OFF_RATING": (80.0, 140.0),
    "DEF_RATING": (80.0, 140.0),
    "PACE": (80.0, 120.0),
    "EFG_PCT": (0.30, 0.80),
    "OREB_PCT": (0.0, 0.65),
}
RECENT_LIMITS = {key: ADVANCED_LIMITS[key]
                 for key in ("OFF_RATING", "DEF_RATING", "PACE")}


def _number(row: dict[str, Any], field: str, *, low: float, high: float,
            source: str) -> float:
    if field not in row or row[field] in (None, ""):
        raise ValueError(f"{source}: missing {field}")
    try:
        number = float(row[field])
    except (TypeError, ValueError):
        raise ValueError(f"{source}: nonnumeric {field}") from None
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"{source}: {field} outside [{low},{high}]")
    return number


def _unique_team(
    rows: Any, team: str, *, source: str, required: bool = True
) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        raise ValueError(f"{source}: expected list of NBA team rows")
    matches = [
        row for row in rows
        if isinstance(row, dict) and canonical_team(str(row.get("TEAM_NAME") or "")) == team
    ]
    if len(matches) > 1:
        raise ValueError(f"{source}: duplicate {team} rows")
    if not matches:
        if required:
            raise ValueError(f"{source}: missing {team}")
        return None
    row = matches[0]
    provider_team_id = row.get("TEAM_ID")
    if provider_team_id not in (None, ""):
        try:
            valid = int(provider_team_id) == team_info(team).team_id
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise ValueError(f"{source}: {team} TEAM_ID mismatch")
    return row


def _tov_rate(row: dict[str, Any], *, source: str) -> float:
    field = "TM_TOV_PCT" if row.get("TM_TOV_PCT") not in (None, "") else "TOV_PCT"
    raw = _number(row, field, low=0.0, high=35.0, source=source)
    fraction = raw / 100.0 if raw > 1.0 else raw
    if not 0.03 <= fraction <= 0.30:
        raise ValueError(f"{source}: turnover rate outside NBA bounds")
    return fraction


def validate_team_stats(
    team_name: str, *,
    advanced_windows: dict[int | str, list[dict[str, Any]]],
    base_season: list[dict[str, Any]],
    min_games: int = 5,
) -> dict[str, Any]:
    team = team_info(team_name).name
    if not isinstance(advanced_windows, dict):
        raise ValueError("advanced_windows must be a dictionary")
    windows = {int(key): rows for key, rows in advanced_windows.items()}
    season = _unique_team(windows.get(0), team, source="season_advanced")
    source = f"season_advanced:{team}"
    gp = _number(season, "GP", low=0, high=100, source=source)
    if not gp.is_integer() or gp < min_games:
        raise ValueError(f"{source}: insufficient GP ({gp} < {min_games})")
    for field, bounds in ADVANCED_LIMITS.items():
        _number(season, field, low=bounds[0], high=bounds[1], source=source)
    _tov_rate(season, source=source)
    for window in (30, 15, 10, 5):
        if window not in windows:
            continue  # Optional in offline research; required upstream for full live data.
        current = _unique_team(windows[window], team, source=f"last{window}_advanced")
        for field, bounds in RECENT_LIMITS.items():
            _number(current, field, low=bounds[0], high=bounds[1],
                    source=f"last{window}_advanced:{team}")
    base = _unique_team(base_season, team, source="season_base")
    fga = _number(base, "FGA", low=1, high=150, source=f"season_base:{team}")
    fg3a = _number(base, "FG3A", low=0, high=fga, source=f"season_base:{team}")
    fta = _number(base, "FTA", low=0, high=100, source=f"season_base:{team}")
    if fta / fga > 1.2:
        raise ValueError(f"season_base:{team}: implausible free-throw rate")
    return {
        "team": team, "gp": int(gp), "recent_windows": sorted(k for k in windows if k),
        "three_pa_rate": fg3a / fga, "ft_rate": fta / fga,
        "tov_rate": _tov_rate(season, source=source),
    }


def _roster(
    rows: Any, team_name: str, *, source: str, minimum_players: int
) -> set[int]:
    team = team_info(team_name)
    if not isinstance(rows, list):
        raise ValueError(f"{source}: player rows must be a list")
    ids: set[int] = set()
    qualified: set[int] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{source}: player row must be an object")
        if str(row.get("TEAM_ID") or "") != str(team.team_id):
            continue
        try:
            pid = int(row["PLAYER_ID"])
        except (ValueError, TypeError, KeyError):
            raise ValueError(f"{source}:{team.name}: missing numeric PLAYER_ID") from None
        if pid in ids:
            raise ValueError(f"{source}:{team.name}: duplicate PLAYER_ID {pid}")
        ids.add(pid)
        if not str(row.get("PLAYER_NAME") or "").strip():
            raise ValueError(f"{source}:{team.name}: missing PLAYER_NAME")
        minutes = _number(row, "MIN", low=0, high=48,
                          source=f"{source}:{team.name}:{pid}")
        if minutes > 0:
            qualified.add(pid)
    if len(qualified) < minimum_players:
        raise ValueError(f"{source}:{team.name}: insufficient active player-minute coverage")
    return qualified


def validate_game_stat_pack(
    pack: dict[str, Any], home: str, away: str, *,
    min_team_games: int = 5, strict_live: bool = True,
) -> dict[str, Any]:
    """Check both teams before spending odds credits or projecting a score."""
    if not isinstance(pack, dict):
        raise ValueError("statistics pack must be a dictionary")
    if str(home) == str(away):
        raise ValueError("home and away must differ")
    advanced = pack.get("advanced_windows") or {}
    if strict_live and any(str(window) not in {str(k) for k in advanced}
                           for window in (0, 30, 15, 10, 5)):
        raise ValueError("live statistics missing required temporal windows")
    teams = {}
    for team in (home, away):
        teams[team] = validate_team_stats(
            team, advanced_windows=advanced,
            base_season=pack.get("base_season"),
            min_games=min_team_games,
        )
        season_players = _roster(pack.get("player_season"), team,
                                 source="season_players", minimum_players=6)
        recent_players = _roster(pack.get("player_recent"), team,
                                 source="recent_players", minimum_players=6)
        if strict_live:
            advanced_players = pack.get("player_advanced")
            if not isinstance(advanced_players, list):
                raise ValueError("live player advanced rows missing")
            matching = {
                int(row["PLAYER_ID"]) for row in advanced_players
                if isinstance(row, dict)
                and str(row.get("TEAM_ID") or "") == str(team_info(team).team_id)
                and row.get("PLAYER_ID") is not None
            }
            if len(season_players & recent_players & matching) < 6:
                raise ValueError(f"player_advanced:{team}: insufficient matching players")
        teams[team]["season_players"] = len(season_players)
        teams[team]["recent_players"] = len(recent_players)
    return {"eligible": True, "teams": teams, "strict_live": strict_live}
