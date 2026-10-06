from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timezone
import os
from typing import Any

from .provider_http import get_json
from .teams import canonical_team

DEFAULT_SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
LEGACY_SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"
DEFAULT_SCHEDULE_URLS = (DEFAULT_SCHEDULE_URL, LEGACY_SCHEDULE_URL)
LEGACY_DATA_SCHEDULE_TEMPLATE = (
    "https://data.nba.com/data/10s/v2015/json/mobile_teams/nba/"
    "{season_start}/league/00_full_schedule.json"
)


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


def _date(value: Any) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(
                s[:19] if fmt == "%Y-%m-%d" else s, fmt
            ).date().isoformat()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return s[:10]


def _score(team: dict[str, Any]) -> int | None:
    for key in ("score", "points", "s"):
        value = team.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except Exception:
                pass
    return None


def _team_name(team: dict[str, Any], *, legacy: bool = False) -> str:
    if legacy:
        city = str(team.get("tc") or "")
        name = str(team.get("tn") or "")
    else:
        city = str(team.get("teamCity") or "")
        name = str(team.get("teamName") or team.get("team_name") or "")
    candidate = canonical_team(name)
    if city and candidate and not candidate.startswith(city):
        candidate = canonical_team(f"{city} {candidate}")
    return candidate


def parse_schedule(payload: dict[str, Any]) -> list[ScheduleGame]:
    league = (
        payload.get("leagueSchedule")
        or payload.get("league_schedule")
        or payload
    )
    dates = league.get("gameDates") or league.get("game_dates") or []
    games: list[ScheduleGame] = []
    for day in dates:
        fallback = _date(day.get("gameDate") or day.get("game_date"))
        for raw in day.get("games") or []:
            home = raw.get("homeTeam") or {}
            away = raw.get("awayTeam") or {}
            commence = str(
                raw.get("gameDateTimeUTC")
                or raw.get("gameTimeUTC")
                or raw.get("gameDateTimeEst")
                or ""
            )
            games.append(
                ScheduleGame(
                    str(raw.get("gameId") or raw.get("game_id") or ""),
                    fallback or _date(commence),
                    commence,
                    _team_name(home),
                    _team_name(away),
                    int(raw.get("gameStatus") or raw.get("game_status") or 0),
                    str(
                        raw.get("gameStatusText")
                        or raw.get("game_status_text")
                        or ""
                    ),
                    _score(home),
                    _score(away),
                )
            )
    return [
        game for game in games
        if game.game_id and game.home and game.away and game.game_date
    ]


def _legacy_status(raw: dict[str, Any]) -> int:
    value = raw.get("st")
    try:
        parsed = int(value)
        if parsed in {1, 2, 3}:
            return parsed
    except (TypeError, ValueError):
        pass
    text = str(raw.get("stt") or "").casefold()
    if "final" in text:
        return 3
    if any(token in text for token in ("q1", "q2", "q3", "q4", "half", "ot")):
        return 2
    return 1


def parse_legacy_data_schedule(payload: dict[str, Any]) -> list[ScheduleGame]:
    """Parse the official data.nba.com mobile full-season schedule."""
    root = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    months = root.get("lscd") or []
    games: list[ScheduleGame] = []
    for month in months:
        schedule = month.get("mscd") or {}
        for raw in schedule.get("g") or []:
            home = raw.get("h") or {}
            away = raw.get("v") or {}
            utc_date = _date(raw.get("gdtutc"))
            utc_time = str(raw.get("utctm") or "").strip()
            commence = (
                f"{utc_date}T{utc_time}:00Z"
                if utc_date and utc_time and len(utc_time.split(":")) == 2
                else str(raw.get("gdtutc") or "")
            )
            games.append(
                ScheduleGame(
                    str(raw.get("gid") or ""),
                    _date(raw.get("gdte")) or utc_date,
                    commence,
                    _team_name(home, legacy=True),
                    _team_name(away, legacy=True),
                    _legacy_status(raw),
                    str(raw.get("stt") or ""),
                    _score(home),
                    _score(away),
                )
            )
    return [
        game for game in games
        if game.game_id and game.home and game.away and game.game_date
    ]


def season_for_date(value: str | date | datetime) -> str:
    if isinstance(value, str):
        d = date.fromisoformat(_date(value))
    elif isinstance(value, datetime):
        d = value.date()
    else:
        d = value
    start = d.year if d.month >= 7 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def legacy_data_schedule_url(value: str | date | datetime | None = None) -> str:
    current = value or datetime.now(timezone.utc)
    season = season_for_date(current)
    return LEGACY_DATA_SCHEDULE_TEMPLATE.format(season_start=season[:4])


def fetch_schedule_with_source(
    *, url: str | None = None
) -> tuple[list[ScheduleGame], str]:
    configured = url or os.environ.get("NBA_SCHEDULE_URL")
    if configured:
        candidates = ((configured, "CONFIGURED", parse_schedule),)
    else:
        candidates = (
            (DEFAULT_SCHEDULE_URL, "NBA_CDN_CURRENT", parse_schedule),
            (LEGACY_SCHEDULE_URL, "NBA_CDN_LEGACY", parse_schedule),
            (
                legacy_data_schedule_url(),
                "NBA_DATA_MOBILE",
                parse_legacy_data_schedule,
            ),
        )
    failures: list[str] = []
    for candidate, source, parser in candidates:
        try:
            payload = get_json(candidate)
            if not isinstance(payload, dict):
                raise RuntimeError("NBA schedule payload is not an object")
            games = parser(payload)
            if not games:
                raise RuntimeError("NBA schedule payload contained no games")
            return games, source
        except Exception as exc:
            failures.append(f"{candidate}:{type(exc).__name__}:{exc}")
    raise RuntimeError(
        "NBA schedule unavailable across official routes: " + " | ".join(failures)
    )


def fetch_schedule(*, url: str | None = None) -> list[ScheduleGame]:
    games, _ = fetch_schedule_with_source(url=url)
    return games


def games_on(games: list[ScheduleGame], target: str | date) -> list[ScheduleGame]:
    target_s = target.isoformat() if isinstance(target, date) else _date(target)
    return [game for game in games if game.game_date == target_s]
