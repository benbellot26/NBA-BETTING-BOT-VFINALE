from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from io import BytesIO
import re
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from .injury_report import InjuryRecord
from .provider_http import get_bytes, get_text
from .teams import TEAMS, canonical_team

PDF_LINK_RE = re.compile(r'href=["\']([^"\']*Injury-Report_[^"\']+\.pdf)["\']', re.I)
REPORT_TS_RE = re.compile(r"Injury-Report_(\d{4})-(\d{2})-(\d{2})_(\d{2})_(\d{2})(AM|PM)", re.I)
DATE_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
MATCHUP_RE = re.compile(r"\b([A-Z]{3})@([A-Z]{3})\b")
PLAYER_RE = re.compile(
    r"^(?P<family>[\wÀ-ÖØ-öø-ÿ.'’\-]+(?:\s+[\wÀ-ÖØ-öø-ÿ.'’\-]+)*),\s*"
    r"(?P<given>[\wÀ-ÖØ-öø-ÿ.'’\-]+(?:\s+[\wÀ-ÖØ-öø-ÿ.'’\-]+)*)\s+"
    r"(?P<status>Available|Probable|Questionable|Doubtful|Out)\b\s*(?P<reason>.*)",
    re.I,
)


def injury_page_url(season: str) -> str:
    return f"https://official.nba.com/nba-injury-report-{season}-season/"


def discover_report_links(html: str, base_url: str) -> list[str]:
    return list(dict.fromkeys(urljoin(base_url, link) for link in PDF_LINK_RE.findall(html)))


def _report_dt(url: str) -> datetime:
    match = REPORT_TS_RE.search(url)
    if match is None:
        raise ValueError("official injury report URL lacks timestamp")
    year, month, day, hour, minute, ampm = match.groups()
    hh = int(hour) % 12 + (12 if ampm.upper() == "PM" else 0)
    return datetime(int(year), int(month), int(day), hh, int(minute), tzinfo=ZoneInfo("America/New_York"))


def latest_report_url(*, season: str, page_url: str | None = None) -> str:
    page = page_url or injury_page_url(season)
    links = discover_report_links(get_text(page, headers={"Accept": "text/html,*/*"}), page)
    valid = [(link, _report_dt(link)) for link in links if REPORT_TS_RE.search(link)]
    if not valid:
        raise RuntimeError("official NBA injury page exposed no timestamped PDF report")
    return max(valid, key=lambda item: item[1])[0]


def extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf is required for official injury PDF acquisition") from None
    return "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(data)).pages)


def canonical_player_name(family: str, given: str) -> str:
    return " ".join(f"{given.strip()} {family.strip()}".split())


def parse_report_document(text: str, *, reported_at: str) -> dict[str, Any]:
    """Parse the published NBA PDF's game-date/team/player rows.

    Explicit NOT YET SUBMITTED teams are not silently treated as healthy.
    Page breaks may omit the team/date; these carry forward until a new row.
    """
    current_date = ""
    current_matchup = ""
    current_team = ""
    records: list[InjuryRecord] = []
    team_status: dict[str, str] = {}
    team_names = sorted(TEAMS, key=len, reverse=True)
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line or line.startswith(("Injury Report:", "Page ", "Game Date ")):
            continue
        day = DATE_RE.search(line)
        if day:
            current_date = datetime.strptime(day.group(1), "%m/%d/%Y").date().isoformat()
        matchup = MATCHUP_RE.search(line)
        if matchup:
            current_matchup = matchup.group(0)
        hit = next((re.search(r"(?<![\w])" + re.escape(team) + r"(?![\w])", line)
                    for team in team_names
                    if re.search(r"(?<![\w])" + re.escape(team) + r"(?![\w])", line)), None)
        if hit is not None:
            current_team = canonical_team(hit.group(0))
            fragment = line[hit.end():].strip()
        else:
            fragment = line
        if not current_team:
            continue
        key = f"{current_date}|{current_team}"
        if "NOT YET SUBMITTED" in fragment.upper():
            team_status[key] = "NOT_YET_SUBMITTED"
            continue
        if "NO INJURIES REPORTED" in fragment.upper():
            team_status[key] = "SUBMITTED"
            continue
        match = PLAYER_RE.match(fragment)
        if match is None:
            continue
        if team_status.get(key) == "NOT_YET_SUBMITTED":
            continue
        team_status[key] = "SUBMITTED"
        name = canonical_player_name(match.group("family"), match.group("given"))
        player_id = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
        records.append(InjuryRecord(
            player_id=player_id, player_name=name, team=current_team,
            status=match.group("status").upper(), reported_at=reported_at,
            reason=match.group("reason").strip(), game_date=current_date, matchup=current_matchup,
        ).validated())
    distinct = {(r.game_date, r.team, r.player_name): r for r in records}
    return {"records": [asdict(row) for row in distinct.values()], "team_status": team_status}


def parse_report_text(text: str, *, reported_at: str) -> list[InjuryRecord]:
    return [InjuryRecord(**row) for row in parse_report_document(text, reported_at=reported_at)["records"]]


def game_report_ready(report: dict[str, Any], *, game_date: str, home: str, away: str) -> bool:
    statuses = report.get("team_status") or {}
    return all(statuses.get(f"{game_date}|{canonical_team(team)}") == "SUBMITTED" for team in (home, away))


def fetch_latest_report(*, season: str, page_url: str | None = None) -> dict[str, Any]:
    url = latest_report_url(season=season, page_url=page_url)
    issued = _report_dt(url).astimezone(timezone.utc).isoformat()
    document = parse_report_document(extract_pdf_text(get_bytes(url, headers={"Accept": "application/pdf"})),
                                     reported_at=issued)
    return {
        "source_url": url, "reported_at": issued,
        "records": document["records"], "team_status": document["team_status"],
        "record_count": len(document["records"]),
    }
