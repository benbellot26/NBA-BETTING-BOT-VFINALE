from __future__ import annotations
from dataclasses import dataclass
from datetime import date,datetime
import os
from typing import Any
from .provider_http import get_json
from .teams import canonical_team

DEFAULT_SCHEDULE_URL="https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"

@dataclass(frozen=True)
class ScheduleGame:
    game_id:str;game_date:str;commence_time:str;home:str;away:str;status:int;status_text:str;home_score:int|None=None;away_score:int|None=None
    @property
    def final(self)->bool:return self.status==3 or "final" in self.status_text.lower()

def _date(value:Any)->str:
    s=str(value or "").strip()
    if not s:return ""
    for fmt in ("%Y-%m-%d","%m/%d/%Y %H:%M:%S","%m/%d/%Y %I:%M:%S %p","%m/%d/%Y"):
        try:return datetime.strptime(s[:19] if fmt=="%Y-%m-%d" else s,fmt).date().isoformat()
        except Exception:pass
    try:return datetime.fromisoformat(s.replace("Z","+00:00")).date().isoformat()
    except Exception:return s[:10]

def _score(team:dict[str,Any])->int|None:
    for key in ("score","points"):
        value=team.get(key)
        if value not in (None,""):
            try:return int(value)
            except Exception:pass
    return None

def parse_schedule(payload:dict[str,Any])->list[ScheduleGame]:
    league=payload.get("leagueSchedule") or payload.get("league_schedule") or payload;dates=league.get("gameDates") or league.get("game_dates") or [];games=[]
    for day in dates:
        fallback=_date(day.get("gameDate") or day.get("game_date"))
        for raw in day.get("games") or []:
            home=raw.get("homeTeam") or {};away=raw.get("awayTeam") or {}
            hn=canonical_team(str(home.get("teamName") or home.get("team_name") or ""));an=canonical_team(str(away.get("teamName") or away.get("team_name") or ""))
            if home.get("teamCity") and hn and not hn.startswith(str(home.get("teamCity"))):hn=canonical_team(f"{home.get('teamCity')} {hn}")
            if away.get("teamCity") and an and not an.startswith(str(away.get("teamCity"))):an=canonical_team(f"{away.get('teamCity')} {an}")
            commence=str(raw.get("gameDateTimeUTC") or raw.get("gameTimeUTC") or raw.get("gameDateTimeEst") or "")
            games.append(ScheduleGame(str(raw.get("gameId") or raw.get("game_id") or ""),fallback or _date(commence),commence,hn,an,int(raw.get("gameStatus") or raw.get("game_status") or 0),str(raw.get("gameStatusText") or raw.get("game_status_text") or ""),_score(home),_score(away)))
    return [g for g in games if g.game_id and g.home and g.away and g.game_date]

def fetch_schedule(*,url:str|None=None)->list[ScheduleGame]:
    payload=get_json(url or os.environ.get("NBA_SCHEDULE_URL") or DEFAULT_SCHEDULE_URL)
    if not isinstance(payload,dict):raise RuntimeError("NBA schedule payload is not an object")
    return parse_schedule(payload)

def games_on(games:list[ScheduleGame],target:str|date)->list[ScheduleGame]:
    target_s=target.isoformat() if isinstance(target,date) else _date(target)
    return [g for g in games if g.game_date==target_s]

def season_for_date(value:str|date|datetime)->str:
    if isinstance(value,str):d=date.fromisoformat(_date(value))
    elif isinstance(value,datetime):d=value.date()
    else:d=value
    start=d.year if d.month>=7 else d.year-1
    return f"{start}-{str(start+1)[-2:]}"
