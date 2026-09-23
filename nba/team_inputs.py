from __future__ import annotations

from typing import Any

from .model import TeamMetrics
from .team_strength import TimeWindow, blend_team_metrics
from .teams import canonical_team


def _num(row: dict[str, Any] | None, key: str, default: float) -> float:
    if not row:
        return default
    value = row.get(key)
    try:
        return float(value)
    except Exception:
        return default


def _by_name(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {canonical_team(str(r.get("TEAM_NAME") or "")): r for r in rows}


def build_team_metrics(
    team_name: str,
    *,
    advanced_windows: dict[int, list[dict[str, Any]]],
    base_season: list[dict[str, Any]] | None = None,
    home: bool = False,
) -> TeamMetrics:
    team = canonical_team(team_name)
    maps = {n: _by_name(rows) for n, rows in advanced_windows.items()}
    season = maps.get(0, {}).get(team)
    if season is None:
        raise ValueError(f"team missing from season stats: {team}")
    def window(key: str, league_default: float) -> TimeWindow:
        return TimeWindow(
            season=_num(season, key, league_default),
            last30=_num(maps.get(30, {}).get(team), key, league_default) if 30 in maps else None,
            last15=_num(maps.get(15, {}).get(team), key, league_default) if 15 in maps else None,
            last10=_num(maps.get(10, {}).get(team), key, league_default) if 10 in maps else None,
            last5=_num(maps.get(5, {}).get(team), key, league_default) if 5 in maps else None,
        )
    base = _by_name(base_season or []).get(team) or {}
    fga = max(1.0, _num(base, "FGA", 88.0))
    style = {
        "efg": _num(season, "EFG_PCT", .55),
        "tov_pct": _num(season, "TM_TOV_PCT", _num(season, "TOV_PCT", 13.0)) / (100.0 if _num(season, "TM_TOV_PCT", 13.0) > 1 else 1.0),
        "orb_pct": _num(season, "OREB_PCT", .25),
        "ft_rate": _num(base, "FTA", 22.0) / fga,
        "three_pa_rate": _num(base, "FG3A", 35.0) / fga,
    }
    return blend_team_metrics(
        team,
        ortg=window("OFF_RATING", 115.0),
        drtg=window("DEF_RATING", 115.0),
        pace=window("PACE", 99.5),
        style=style,
        home=home,
    )
