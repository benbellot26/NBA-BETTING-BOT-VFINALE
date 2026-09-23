from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from io import BytesIO
import re
from typing import Any
from urllib.parse import urljoin

from .injury_report import InjuryRecord
from .provider_http import get_bytes, get_text
from .teams import TEAMS, canonical_team

PDF_LINK_RE=re.compile(r'href=["\']([^"\']*Injury-Report_[^"\']+\.pdf)["\']',re.I)
STATUS_RE=re.compile(r"(?P<player>[A-Za-zÀ-ÖØ-öø-ÿ.'’\- ]+,\s*[A-Za-zÀ-ÖØ-öø-ÿ.'’\- ]+)\s+(?P<status>Available|Probable|Questionable|Doubtful|Out)\s*(?P<reason>.*)",re.I)
MATCHUP_RE=re.compile(r"\b([A-Z]{3})@([A-Z]{3})\b")
DATE_RE=re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
REPORT_TS_RE=re.compile(r"Injury-Report_(\d{4})-(\d{2})-(\d{2})_(\d{2})_(\d{2})(AM|PM)",re.I)


def injury_page_url(season: str) -> str:
    return f"https://official.nba.com/nba-injury-report-{season}-season/"


def discover_report_links(html: str, base_url: str) -> list[str]:
    seen=[]
    for href in PDF_LINK_RE.findall(html):
        url=urljoin(base_url,href)
        if url not in seen: seen.append(url)
    return seen


def _report_dt(url: str) -> datetime:
    m=REPORT_TS_RE.search(url)
    if not m: return datetime.min
    year,month,day,hour,minute,ampm=m.groups()
    h=int(hour)%12+(12 if ampm.upper()=="PM" else 0)
    return datetime(int(year),int(month),int(day),h,int(minute))


def latest_report_url(*, season: str, page_url: str | None=None) -> str:
    page=page_url or injury_page_url(season)
    links=discover_report_links(get_text(page,headers={"Accept":"text/html,*/*"}),page)
    if not links: raise RuntimeError("official NBA injury page exposed no report PDF links")
    return max(links,key=_report_dt)


def extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required for official injury PDF acquisition") from exc
    reader=PdfReader(BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def parse_report_text(text: str, *, reported_at: str) -> list[InjuryRecord]:
    current_team=""
    records=[]
    team_names=sorted(TEAMS, key=len, reverse=True)
    for raw in text.splitlines():
        line=" ".join(raw.split())
        if not line: continue
        for team in team_names:
            if team in line:
                current_team=team
                break
        match=STATUS_RE.search(line)
        if not match or not current_team: continue
        player=" ".join(match.group("player").split())
        status=match.group("status").upper()
        reason=match.group("reason").strip()
        player_id=re.sub(r"[^a-z0-9]+","-",player.lower()).strip("-")
        records.append(InjuryRecord(player_id,player,current_team,status,reported_at,reason).validated())
    dedup={}
    for row in records: dedup[(row.team,row.player_name)]=row
    return list(dedup.values())


def fetch_latest_report(*, season: str, page_url: str | None=None) -> dict[str,Any]:
    url=latest_report_url(season=season,page_url=page_url)
    stamp=_report_dt(url).isoformat()+"Z"
    data=get_bytes(url,headers={"Accept":"application/pdf"})
    text=extract_pdf_text(data)
    rows=parse_report_text(text,reported_at=stamp)
    return {"source_url":url,"reported_at":stamp,"records":[asdict(r) for r in rows],"record_count":len(rows)}
