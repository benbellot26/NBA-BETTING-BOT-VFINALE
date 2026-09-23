from __future__ import annotations

from typing import Any
from urllib.parse import urlencode
from .provider_http import get_json

BASE = "https://stats.nba.com/stats"


def _result_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("resultSet")
    if result is None:
        sets = payload.get("resultSets") or []
        result = sets[0] if sets else None
    if not isinstance(result, dict):
        raise RuntimeError("NBA stats payload missing resultSet")
    headers = result.get("headers") or []
    rows = result.get("rowSet") or []
    return [dict(zip(headers, row)) for row in rows]


def _common(season: str, last_n_games: int, measure_type: str, date_to: str | None = None) -> dict[str, Any]:
    return {
        "College": "", "Conference": "", "Country": "", "DateFrom": "", "DateTo": date_to or "",
        "Division": "", "DraftPick": "", "DraftYear": "", "GameScope": "", "GameSegment": "",
        "Height": "", "LastNGames": int(last_n_games), "LeagueID": "00", "Location": "",
        "MeasureType": measure_type, "Month": 0, "OpponentTeamID": 0, "Outcome": "",
        "PORound": 0, "PaceAdjust": "N", "PerMode": "PerGame", "Period": 0,
        "PlayerExperience": "", "PlayerPosition": "", "PlusMinus": "N", "Rank": "N",
        "Season": season, "SeasonSegment": "", "SeasonType": "Regular Season",
        "ShotClockRange": "", "StarterBench": "", "TeamID": 0, "VsConference": "",
        "VsDivision": "", "Weight": "",
    }


def _fetch(endpoint: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return _result_rows(get_json(f"{BASE}/{endpoint}?{urlencode(params)}", timeout=30.0, retries=2))


def team_stats(*, season: str, last_n_games: int = 0,
               measure_type: str = "Advanced", date_to: str | None = None) -> list[dict[str, Any]]:
    return _fetch("leaguedashteamstats", _common(season, last_n_games, measure_type, date_to))


def player_stats(*, season: str, last_n_games: int = 0,
                 measure_type: str = "Base", date_to: str | None = None) -> list[dict[str, Any]]:
    return _fetch("leaguedashplayerstats", _common(season, last_n_games, measure_type, date_to))


def indexed(rows: list[dict[str, Any]], key: str) -> dict[Any, dict[str, Any]]:
    return {row.get(key): row for row in rows if row.get(key) is not None}
