from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import os
from typing import Any

from .provider_http import get_json
from .teams import canonical_team

DEFAULT_SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"


@dataclass(frozen=True)
class ScheduleGame:
    game_id: str
    game_date: str
    commence_time: str
    home: str
    away: str
    status: int
    status_text: str
    home_score: int | None = None
    away_score: int | None = None

    @property
    def final(self) -> bool:
        return self.status == 3 or "final" in self.status_text.lower()


def _score(team: dict[str, Any]) -> int | None:
    for key in ("score", "points"):
        value = team.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except Exception:
                pass
    return None


def parse_schedule(payload: dict[str, Any]) -> list[ScheduleGame]:
    league = payload.get("leagueSchedule") or payload.get("league_schedule") or payload
    dates = league.get("gameDates") or league.get("game_dates") or []
    games: list[ScheduleGame] = []
    for day in dates:
        fallback_date = str(day.get("gameDate") or day.get("game_date") or "")[:10]
        for raw in day.get("games") or []:
            home = raw.get("homeTeam") or {}
            away = raw.get("awayTeam") or {}
            home_name = canonical_team(str(home.get("teamName") or home.get("team_name") or ""))
            away_name = canonical_team(str(away.get("teamName") or away.get("team_name") or ""))
            if home.get("teamCity") and home_name and not home_name.startswith(str(home.get("teamCity"))):
                home_name = canonical_team(f"{home.get('teamCity')} {home_name}")
            if away.get("teamCity") and away_name and not away_name.startswith(str(away.get("teamCity"))):
                away_name = canonical_team(f"{away.get('teamCity')} {away_name}")
            commence = str(raw.get("gameDateTimeUTC") or raw.get("gameTimeUTC") or raw.get("gameDateTimeEst") or "")
            game_date = fallback_date or commence[:10]
            games.append(ScheduleGame(
                game_id=str(raw.get("gameId") or raw.get("game_id") or ""),
                game_date=game_date,
                commence_time=commence,
                home=home_name,
                away=away_name,
                status=int(raw.get("gameStatus") or raw.get("game_status") or 0),
                status_text=str(raw.get("gameStatusText") or raw.get("game_status_text") or ""),
                home_score=_score(home),
                away_score=_score(away),
            ))
    return [g for g in games if g.game_id and g.home and g.away]


def fetch_schedule(*, url: str | None = None) -> list[ScheduleGame]:
    payload = get_json(url or os.environ.get("NBA_SCHEDULE_URL") or DEFAULT_SCHEDULE_URL)
    if not isinstance(payload, dict):
        raise RuntimeError("NBA schedule payload is not an object")
    return parse_schedule(payload)


def games_on(games: list[ScheduleGame], target: str | date) -> list[ScheduleGame]:
    target_s = target.isoformat() if isinstance(target, date) else str(target)[:10]
    return [g for g in games if g.game_date[:10] == target_s]


def season_for_date(value: str | date | datetime) -> str:
    if isinstance(value, str):
        d = date.fromisoformat(value[:10])
    elif isinstance(value, datetime):
        d = value.date()
    else:
        d = value
    start = d.year if d.month >= 7 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"
