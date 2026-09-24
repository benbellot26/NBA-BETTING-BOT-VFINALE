"""Official NBA Communications regular-season schedule reference.

REFERENCE_ONLY: no official game IDs/final scores, so this cannot replace the
production schedule or outcome provider.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import BytesIO
import json
import re
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
from .provider_http import get_bytes, get_text

PDF_RE=re.compile(r'href=["\']([^"\']*NBA[^"\']*Schedule[^"\']*By-Date[^"\']*\.pdf)["\']',re.I)
ROW_RE=re.compile(
    r"^\s*(?P<number>\d+)\s+(?P<day>Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.\s+"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{2})\s+(?P<team1>.+?)\s+"
    r"(?P<relation>at|vs)\s+(?P<team2>.+?)\s+"
    r"(?P<local>\d{1,2}:\d{2}\s+[AP]M)\s+"
    r"(?P<et>\d{1,2}:\d{2}\s+[AP]M)(?:\s+.*)?$",re.I)

DISPLAY_TEAMS={
"Atlanta":"Atlanta Hawks","Boston":"Boston Celtics","Brooklyn":"Brooklyn Nets",
"Charlotte":"Charlotte Hornets","Chicago":"Chicago Bulls","Cleveland":"Cleveland Cavaliers",
"Dallas":"Dallas Mavericks","Denver":"Denver Nuggets","Detroit":"Detroit Pistons",
"Golden State":"Golden State Warriors","Houston":"Houston Rockets","Indiana":"Indiana Pacers",
"LA Clippers":"LA Clippers","LA Lakers":"Los Angeles Lakers","Memphis":"Memphis Grizzlies",
"Miami":"Miami Heat","Milwaukee":"Milwaukee Bucks","Minnesota":"Minnesota Timberwolves",
"New Orleans":"New Orleans Pelicans","New York":"New York Knicks",
"Oklahoma City":"Oklahoma City Thunder","Orlando":"Orlando Magic",
"Philadelphia":"Philadelphia 76ers","Phoenix":"Phoenix Suns",
"Portland":"Portland Trail Blazers","Sacramento":"Sacramento Kings",
"San Antonio":"San Antonio Spurs","Toronto":"Toronto Raptors","Utah":"Utah Jazz",
"Washington":"Washington Wizards",
}

@dataclass(frozen=True)
class ReferenceScheduleGame:
    reference_id:str
    schedule_number:int
    game_date:str
    commence_time:str
    team1:str
    team2:str
    relation:str
    away:str|None
    home:str|None
    neutral_site:bool

def schedule_release_url(season:str)->str:
    return f"https://pr.nba.com/{season}-nba-regular-season-schedule"

def discover_pdf_url(html:str,base_url:str)->str:
    match=PDF_RE.search(html)
    if match is None: raise RuntimeError("NBA Communications release exposed no schedule-by-date PDF")
    return urljoin(base_url,match.group(1))

def extract_pdf_text(data:bytes)->str:
    try: from pypdf import PdfReader
    except ImportError: raise RuntimeError("pypdf is required for NBA schedule PDF parsing") from None
    return "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(data)).pages)

def _team(value:str)->str:
    clean=" ".join(value.split())
    try:return DISPLAY_TEAMS[clean]
    except KeyError:raise ValueError(f"unknown NBA Communications team label: {clean}") from None

def parse_schedule_text(text:str,*,season:str,minimum_games:int=1000)->list[ReferenceScheduleGame]:
    games=[];seen=set()
    for raw in text.splitlines():
        line=" ".join(raw.split());match=ROW_RE.match(line)
        if match is None:continue
        day=datetime.strptime(match.group("date"),"%m/%d/%y").date()
        et=datetime.strptime(match.group("et"),"%I:%M %p").time()
        eastern=datetime.combine(day,et,tzinfo=ZoneInfo("America/New_York"))
        team1,team2=_team(match.group("team1")),_team(match.group("team2"))
        relation=match.group("relation").lower();neutral=relation=="vs"
        number=int(match.group("number"))
        reference_id=f"nba-pr-{season}-{day.isoformat()}-{number}"
        if reference_id in seen:raise ValueError(f"duplicate NBA Communications reference id: {reference_id}")
        seen.add(reference_id)
        games.append(ReferenceScheduleGame(
            reference_id,number,day.isoformat(),
            eastern.astimezone(timezone.utc).isoformat(),
            team1,team2,relation,team1 if relation=="at" else None,
            team2 if relation=="at" else None,neutral))
    if len(games)<minimum_games:
        raise RuntimeError(f"NBA Communications schedule parsed too few games: {len(games)}")
    return games

def fetch_reference_schedule(*,season:str)->list[ReferenceScheduleGame]:
    release=schedule_release_url(season)
    html=get_text(release,headers={"Accept":"text/html,*/*"},timeout=15.0,retries=1)
    pdf=discover_pdf_url(html,release)
    data=get_bytes(pdf,headers={"Accept":"application/pdf"},timeout=20.0,retries=1)
    return parse_schedule_text(extract_pdf_text(data),season=season)

def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--season",required=True);p.add_argument("--date");p.add_argument("--output")
    a=p.parse_args();games=fetch_reference_schedule(season=a.season)
    if a.date:games=[g for g in games if g.game_date==a.date]
    result={"schema":"pulsar-nba-communications-schedule-v1","role":"OFFICIAL_REFERENCE_ONLY",
            "season":a.season,"game_count":len(games),"games":[asdict(g) for g in games],
            "production_schedule_authority":False,"outcome_authority":False}
    payload=json.dumps(result,indent=2)
    if a.output:
        target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(payload,encoding="utf-8")
    print(payload)
if __name__=="__main__":main()
