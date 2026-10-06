"""Parser for NBA Official Scorer's Report gamebook PDFs.

This module parses the FINAL BOX section from the first few pages of an official
scorer gamebook. It is intentionally separate from live model inputs until a
parity study approves a derived stats adapter.
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
    "away": re.compile(r"VISITOR\s*:\s*([^\n(]+)", re.I),
    "home": re.compile(r"HOME\s*:\s*([^\n(]+)", re.I),
}
TEAM_MINUTES_RE = re.compile(r"^\d{3}:\d{2}$")
INTEGER_RE = re.compile(r"^-?\d+$")


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
    minutes_seconds: int
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


def _expected_team_match(text: str, expected_name: str) -> re.Match[str] | None:
    parts = [re.escape(part) for part in expected_name.split() if part]
    if not parts:
        return None
    return re.search(r"\b" + r"\s+".join(parts) + r"\b", text, re.I)


def _valid_team_minutes(value: str) -> bool:
    seconds = _minutes(value)
    regulation = 240 * 60
    overtime_increment = 25 * 60
    return seconds >= regulation and (seconds - regulation) % overtime_increment == 0


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


def _stream_players(text: str) -> list[PlayerBox]:
    """Parse player rows from whitespace tokens, independent of PDF line breaks."""
    tokens = text.split()
    players: list[PlayerBox] = []
    index = 0
    while index < len(tokens):
        jersey = tokens[index]
        if not (jersey.isdigit() and 1 <= len(jersey) <= 2):
            index += 1
            continue
        # A real player row reaches its MM:SS minutes token within a short
        # name/position span. Stat cells from the preceding row do not.
        limit = min(len(tokens), index + 10)
        time_index = next(
            (j for j in range(index + 2, limit) if TIME_RE.fullmatch(tokens[j])),
            None,
        )
        if time_index is None:
            index += 1
            continue
        stat_tokens = tokens[time_index + 1:time_index + 1 + len(STAT_KEYS)]
        if len(stat_tokens) != len(STAT_KEYS) or not all(
            INTEGER_RE.fullmatch(value) for value in stat_tokens
        ):
            index += 1
            continue
        name_tokens = tokens[index + 1:time_index]
        if name_tokens and name_tokens[-1].upper() in POSITION_CODES:
            name_tokens = name_tokens[:-1]
        name = " ".join(name_tokens).strip()
        if not name:
            index += 1
            continue
        players.append(PlayerBox(
            jersey=jersey,
            name=name,
            minutes_seconds=_minutes(tokens[time_index]),
            stats=_stats(stat_tokens),
        ))
        index = time_index + 1 + len(STAT_KEYS)
    return players


def _parse_team_segment(
    *, text: str, side: str, expected_name: str,
) -> TeamBox:
    header = HEADER_RE[side].search(text)
    if header is not None:
        observed = " ".join(header.group(1).split()).strip()
        if _normalize_team(observed) != _normalize_team(expected_name):
            raise ValueError(
                f"gamebook {side} team mismatch: {observed!r} != {expected_name!r}"
            )
    elif _expected_team_match(text, expected_name) is not None:
        observed = expected_name
    else:
        raise ValueError(f"missing {side} team header in gamebook")

    line_players = [
        player for line in text.splitlines()
        if (player := _player_line(line)) is not None
    ]
    stream_players = _stream_players(text)
    candidates = stream_players if len(stream_players) > len(line_players) else line_players
    deduped: list[PlayerBox] = []
    seen_players: set[tuple[str, str]] = set()
    for player in candidates:
        key = (player.jersey, player.name.casefold())
        if key in seen_players:
            continue
        seen_players.add(key)
        deduped.append(player)
    players = tuple(deduped)
    if len(players) < 5:
        raise ValueError(f"too few active {side} players in gamebook")

    player_points = sum(player.stats["PTS"] for player in players)
    player_minutes = sum(player.minutes_seconds for player in players)
    tokens = text.split()
    total_candidates: list[tuple[str, dict[str, int]]] = []
    for index, token in enumerate(tokens):
        if not TEAM_MINUTES_RE.fullmatch(token):
            continue
        raw_stats = tokens[index + 1:index + 1 + len(STAT_KEYS)]
        if len(raw_stats) != len(STAT_KEYS) or not all(
            INTEGER_RE.fullmatch(value) for value in raw_stats
        ):
            continue
        if not _valid_team_minutes(token):
            continue
        total_candidates.append((token, _stats(raw_stats)))

    reconciled = [
        (token, totals)
        for token, totals in total_candidates
        if totals["PTS"] == player_points
        and abs(player_minutes - _minutes(token)) <= 5
    ]
    if not reconciled:
        if not total_candidates:
            raise ValueError(f"missing valid {side} team total row in gamebook")
        raise ValueError(f"{side} team total does not reconcile to parsed players")

    team_minutes_token, totals = reconciled[0]
    return TeamBox(
        side=side,
        observed_name=observed,
        expected_name=expected_name,
        minutes_seconds=_minutes(team_minutes_token),
        totals=totals,
        players=players,
    )


def parse_final_box_text(
    text: str, *, expected_away: str, expected_home: str,
) -> dict[str, Any]:
    normalized = str(text).replace("\r", "")
    visitor_at = re.search(r"VISITOR\s*:", normalized, re.I)
    home_at = re.search(r"HOME\s*:", normalized, re.I)

    if visitor_at is not None and home_at is not None:
        away_start = visitor_at.start()
        home_start = home_at.start()
    else:
        away_name = _expected_team_match(normalized, expected_away)
        home_name = _expected_team_match(normalized, expected_home)
        if away_name is None or home_name is None:
            raise ValueError("gamebook final-box team sections are incomplete")
        away_start = away_name.start()
        home_start = home_name.start()

    if away_start >= home_start:
        raise ValueError("gamebook final-box team sections are out of order")

    score_at = re.search(r"SCORE\s+BY", normalized[home_start:], re.I)
    home_end = (
        home_start + score_at.start()
        if score_at is not None
        else len(normalized)
    )
    away_text = normalized[away_start:home_start]
    home_text = normalized[home_start:home_end]
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


def _page_text(page: Any) -> str:
    """Prefer whichever pypdf extraction mode preserves more FINAL BOX markers."""
    candidates: list[str] = []
    try:
        candidates.append(page.extract_text(extraction_mode="layout") or "")
    except (TypeError, ValueError, NotImplementedError):
        pass
    try:
        candidates.append(page.extract_text() or "")
    except (TypeError, ValueError, NotImplementedError):
        pass
    if not candidates:
        return ""

    def score(text: str) -> tuple[int, int]:
        upper = text.upper()
        markers = sum(
            token in upper
            for token in ("FINAL BOX", "VISITOR:", "HOME:", "SCORE BY")
        )
        return markers, len(text)

    return max(candidates, key=score)


def extract_final_box_text(data: bytes, *, max_pages: int = 4) -> str:
    """Extract enough consecutive pages to contain a complete FINAL BOX.

    Most NBA gamebooks put the table on page 1, but some preseason PDFs insert
    a cover or split the final box across pages. Scan only the first few pages,
    start at the first FINAL BOX marker, and stop as soon as the four structural
    markers needed by the strict parser are present.
    """
    if not data.startswith(b"%PDF"):
        raise ValueError("gamebook response is not a PDF")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf is required for gamebook parsing") from None
    reader = PdfReader(BytesIO(data))
    if not reader.pages:
        raise ValueError("gamebook PDF has no pages")

    extracted = [
        _page_text(reader.pages[index])
        for index in range(min(len(reader.pages), max_pages))
    ]
    start = next(
        (index for index, text in enumerate(extracted) if "FINAL BOX" in text.upper()),
        0,
    )
    combined: list[str] = []
    for text in extracted[start:]:
        combined.append(text)
        joined = "\n".join(combined)
        upper = joined.upper()
        if all(
            marker in upper
            for marker in ("FINAL BOX", "VISITOR:", "HOME:", "SCORE BY")
        ):
            return joined
    return "\n".join(combined)


def extract_first_page(data: bytes) -> str:
    """Backward-compatible wrapper; now returns the complete FINAL BOX text."""
    return extract_final_box_text(data)


def parse_gamebook_pdf(
    data: bytes, *, expected_away: str, expected_home: str,
) -> dict[str, Any]:
    return parse_final_box_text(
        extract_final_box_text(data),
        expected_away=expected_away,
        expected_home=expected_home,
    )
