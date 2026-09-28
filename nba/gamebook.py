"""Parser for NBA Official Scorer's Report gamebook PDFs.

This module parses only the FINAL BOX first page. It is intentionally separate
from live model inputs until a parity study approves a derived stats adapter.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
import re
from typing import Any

from .teams import team_info

STAT_KEYS = (
    "FG", "FGA", "FG3M", "FG3A", "FT", "FTA", "OREB", "DREB",
    "REB", "AST", "PF", "STL", "TOV", "BLK", "PLUS_MINUS", "PTS",
)
POSITION_CODES = {
    "F", "G", "C", "F-C", "C-F", "G-F", "F-G", "G-C", "C-G",
}
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
HEADER_RE = {
    "away": re.compile(r"VISITOR:\s*([^\n(]+)", re.I),
    "home": re.compile(r"HOME:\s*([^\n(]+)", re.I),
}
TEAM_TOTAL_RE = re.compile(
    r"^240:00\s+"
    + r"\s+".join([r"(-?\d+)"] * len(STAT_KEYS))
    + r"\s*$"
)


@dataclass(frozen=True)
class PlayerBox:
    jersey: str
    name: str
    minutes_seconds: int
    stats: dict[str, int]


@dataclass(frozen=True)
class TeamBox:
    side: str
    observed_name: str
    expected_name: str
    totals: dict[str, int]
    players: tuple[PlayerBox, ...]


def gamebook_url(*, game_date: str, away: str, home: str) -> str:
    compact = str(game_date).replace("-", "")
    if not re.fullmatch(r"\d{8}", compact):
        raise ValueError("gamebook date must be YYYY-MM-DD or YYYYMMDD")
    away_code = team_info(away).tricode
    home_code = team_info(home).tricode
    return (
        f"https://statsdmz.nba.com/pdfs/{compact}/"
        f"{compact}_{away_code}{home_code}_book.pdf"
    )


def _normalize_team(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _minutes(value: str) -> int:
    minute, second = value.split(":", 1)
    return 60 * int(minute) + int(second)


def _stats(values: list[str]) -> dict[str, int]:
    if len(values) != len(STAT_KEYS):
        raise ValueError("unexpected gamebook stat width")
    try:
        parsed = [int(value) for value in values]
    except ValueError:
        raise ValueError("non-integer value in gamebook stat row") from None
    return dict(zip(STAT_KEYS, parsed))


def _player_line(line: str) -> PlayerBox | None:
    tokens = line.split()
    if len(tokens) < 2 or not tokens[0].isdigit():
        return None
    time_index = next(
        (index for index, token in enumerate(tokens) if TIME_RE.fullmatch(token)),
        None,
    )
    if time_index is None:
        return None
    after = tokens[time_index + 1:]
    if len(after) != len(STAT_KEYS):
        return None
    try:
        stats = _stats(after)
    except ValueError:
        return None
    name_tokens = tokens[1:time_index]
    if name_tokens and name_tokens[-1].upper() in POSITION_CODES:
        name_tokens = name_tokens[:-1]
    name = " ".join(name_tokens).strip()
    if not name:
        return None
    return PlayerBox(
        jersey=tokens[0],
        name=name,
        minutes_seconds=_minutes(tokens[time_index]),
        stats=stats,
    )


def _parse_team_segment(
    *, text: str, side: str, expected_name: str,
) -> TeamBox:
    header = HEADER_RE[side].search(text)
    if header is None:
        raise ValueError(f"missing {side} team header in gamebook")
    observed = " ".join(header.group(1).split()).strip()
    if _normalize_team(observed) != _normalize_team(expected_name):
        raise ValueError(
            f"gamebook {side} team mismatch: {observed!r} != {expected_name!r}"
        )
    total_match = next(
        (TEAM_TOTAL_RE.fullmatch(line.strip()) for line in text.splitlines()
         if TEAM_TOTAL_RE.fullmatch(line.strip())),
        None,
    )
    if total_match is None:
        raise ValueError(f"missing {side} team total row in gamebook")
    totals = _stats(list(total_match.groups()))
    players = tuple(
        player for line in text.splitlines()
        if (player := _player_line(line)) is not None
    )
    if len(players) < 5:
        raise ValueError(f"too few active {side} players in gamebook")
    if sum(player.stats["PTS"] for player in players) != totals["PTS"]:
        raise ValueError(f"{side} player points do not reconcile to team total")
    return TeamBox(
        side=side,
        observed_name=observed,
        expected_name=expected_name,
        totals=totals,
        players=players,
    )


def parse_final_box_text(
    text: str, *, expected_away: str, expected_home: str,
) -> dict[str, Any]:
    normalized = str(text).replace("\r", "")
    if "FINAL BOX" not in normalized.upper():
        raise ValueError("gamebook does not contain FINAL BOX")
    visitor_at = re.search(r"VISITOR:", normalized, re.I)
    home_at = re.search(r"HOME:", normalized, re.I)
    score_at = re.search(r"SCORE\s+BY", normalized, re.I)
    if visitor_at is None or home_at is None or score_at is None:
        raise ValueError("gamebook final-box sections are incomplete")
    if not (visitor_at.start() < home_at.start() < score_at.start()):
        raise ValueError("gamebook final-box sections are out of order")
    away_text = normalized[visitor_at.start():home_at.start()]
    home_text = normalized[home_at.start():score_at.start()]
    away_box = _parse_team_segment(
        text=away_text, side="away", expected_name=expected_away
    )
    home_box = _parse_team_segment(
        text=home_text, side="home", expected_name=expected_home
    )
    if away_box.totals["PTS"] < 0 or home_box.totals["PTS"] < 0:
        raise ValueError("negative final score in gamebook")
    return {
        "schema": "pulsar-nba-gamebook-final-box-v1",
        "source": "NBA_OFFICIAL_SCORERS_REPORT",
        "away": asdict(away_box),
        "home": asdict(home_box),
        "away_score": away_box.totals["PTS"],
        "home_score": home_box.totals["PTS"],
    }


def extract_first_page(data: bytes) -> str:
    if not data.startswith(b"%PDF"):
        raise ValueError("gamebook response is not a PDF")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf is required for gamebook parsing") from None
    reader = PdfReader(BytesIO(data))
    if not reader.pages:
        raise ValueError("gamebook PDF has no pages")
    return reader.pages[0].extract_text() or ""


def parse_gamebook_pdf(
    data: bytes, *, expected_away: str, expected_home: str,
) -> dict[str, Any]:
    return parse_final_box_text(
        extract_first_page(data),
        expected_away=expected_away,
        expected_home=expected_home,
    )
