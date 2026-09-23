from __future__ import annotations

from datetime import date, datetime, timezone
import math
from zoneinfo import ZoneInfo

from .model import GameContext
from .schedule import ScheduleGame
from .teams import team_info


def _day(value: str) -> date:
    return date.fromisoformat(value[:10])


def _distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    r=6371.0088
    p1=math.radians(a_lat); p2=math.radians(b_lat)
    dp=math.radians(b_lat-a_lat); dl=math.radians(b_lon-a_lon)
    h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(min(1.0,math.sqrt(h)))


def _venue_team(game: ScheduleGame) -> str:
    return game.home


def _history(team: str, games: list[ScheduleGame], target_date: str) -> list[ScheduleGame]:
    d=_day(target_date)
    return sorted([g for g in games if _day(g.game_date)<d and team in {g.home,g.away}], key=lambda g:g.game_date)


def _team_context(team: str, current_home: str, games: list[ScheduleGame], target_date: str) -> tuple[float,bool,bool,float,float]:
    hist=_history(team,games,target_date)
    if not hist:
        return 3.0,False,False,0.0,0.0
    target=_day(target_date); last=hist[-1]; last_day=_day(last.game_date)
    rest=max(0.0,float((target-last_day).days-1))
    b2b=(target-last_day).days==1
    recent=sum(1 for g in hist if 1 <= (target-_day(g.game_date)).days <= 3)
    three_in_four=recent>=2
    previous_venue=team_info(_venue_team(last))
    current_venue=team_info(current_home)
    travel=_distance_km(previous_venue.latitude,previous_venue.longitude,current_venue.latitude,current_venue.longitude)
    noon=datetime.combine(target,datetime.min.time(),tzinfo=timezone.utc)
    prev_offset=noon.astimezone(ZoneInfo(previous_venue.timezone)).utcoffset()
    curr_offset=noon.astimezone(ZoneInfo(current_venue.timezone)).utcoffset()
    shift=((curr_offset-prev_offset).total_seconds()/3600.0) if prev_offset is not None and curr_offset is not None else 0.0
    return rest,b2b,three_in_four,travel,shift


def build_game_context(game: ScheduleGame, games: list[ScheduleGame], *, analyzed_at: str, phase: str="EARLY") -> GameContext:
    h=_team_context(game.home,game.home,games,game.game_date)
    a=_team_context(game.away,game.home,games,game.game_date)
    venue=team_info(game.home)
    return GameContext(
        game_id=game.game_id, game_date=game.game_date, analyzed_at=analyzed_at,
        home=game.home, away=game.away,
        home_rest_days=h[0], away_rest_days=a[0],
        home_b2b=h[1], away_b2b=a[1],
        home_three_in_four=h[2], away_three_in_four=a[2],
        home_travel_km=h[3], away_travel_km=a[3],
        home_timezone_shift=h[4], away_timezone_shift=a[4],
        altitude_m=venue.altitude_m, phase=phase,
    )
