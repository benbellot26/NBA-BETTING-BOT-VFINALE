"""Reference-only NBA schedule discovery from ESPN's public scoreboard.

This module exists only to discover game identity/date/time for the official
NBA gamebook research path when NBA-hosted schedule endpoints reject hosted
runner egress. It is never a production schedule/outcome authority and never
contributes basketball features, injury data, market prices or betting signals.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from .communications_schedule import ReferenceScheduleGame
from .provider_http import get_json
from .teams import canonical_team

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ROLE = "REFERENCE_SCHEDULE_ONLY"
SOURCE = "ESPN_PUBLIC_SCOREBOARD"


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("ESPN event timestamp requires timezone")
    return parsed


def _team(competitor: dict[str, Any]) -> str:
    team = competitor.get("team") or {}
    name = str(
        team.get("displayName")
        or team.get("shortDisplayName")
        or team.get("name")
        or ""
    )
    return canonical_team(name)


def parse_scoreboard(payload: dict[str, Any]) -> list[ReferenceScheduleGame]:
    games: list[ReferenceScheduleGame] = []
    for index, event in enumerate(payload.get("events") or [], start=1):
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        competition = competitions[0]
        competitors = competition.get("competitors") or []
        home_row = next(
            (row for row in competitors if row.get("homeAway") == "home"),
            None,
        )
        away_row = next(
            (row for row in competitors if row.get("homeAway") == "away"),
            None,
        )
        if not isinstance(home_row, dict) or not isinstance(away_row, dict):
            continue
        home = _team(home_row)
        away = _team(away_row)
        event_id = str(event.get("id") or competition.get("id") or "").strip()
        commence = str(event.get("date") or competition.get("date") or "").strip()
        if not event_id or not commence or not home or not away:
            continue
        tip = _dt(commence)
        game_date = tip.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        games.append(
            ReferenceScheduleGame(
                reference_id=f"espn-{event_id}",
                schedule_number=index,
                game_date=game_date,
                commence_time=tip.isoformat(),
                team1=away,
                team2=home,
                relation="at",
                away=away,
                home=home,
                neutral_site=False,
            )
        )
    return games


def _month_keys(start: date, end: date) -> list[str]:
    if end < start:
        raise ValueError("reference schedule end date precedes start date")
    keys: list[str] = []
    cursor = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while cursor <= last:
        keys.append(cursor.strftime("%Y%m"))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return keys


def fetch_reference_schedule(
    *,
    start_date: str,
    end_date: str,
) -> list[ReferenceScheduleGame]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    rows: dict[str, ReferenceScheduleGame] = {}
    for month in _month_keys(start, end):
        query = urlencode({"dates": month, "limit": 1000})
        payload = get_json(
            f"{BASE_URL}?{query}",
            headers={
                "Accept": "application/json",
                "User-Agent": "pulsar-nba-reference/1.0",
            },
            timeout=12.0,
            retries=1,
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            raise RuntimeError("ESPN scoreboard payload missing events array")
        for game in parse_scoreboard(payload):
            day = date.fromisoformat(game.game_date)
            if start <= day <= end:
                rows[game.reference_id] = game
    return sorted(rows.values(), key=lambda row: (row.game_date, row.commence_time, row.reference_id))
