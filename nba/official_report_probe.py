"""Probe official NBA report surfaces that remain reachable when stats.nba.com is blocked.

NETWORK_DIAGNOSTIC_ONLY. This module never returns predictive rows, never
authorizes a provider, and persists only hashes/structure signals.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .gamebook import parse_gamebook_pdf
from .injury_pdf import injury_page_url
from .provider_http import get_bytes, get_text
from .schedule import season_for_date

# Fixed historical Official Scorer's Reports make runner diagnostics
# deterministic and exercise regular-season + Finals layouts.
KNOWN_GAMEBOOKS = (
    {
        "name": "2025_finals_ind_okc",
        "url": "https://statsdmz.nba.com/pdfs/20250605/20250605_INDOKC_book.pdf",
        "away": "Indiana Pacers", "home": "Oklahoma City Thunder",
        "away_score": 111, "home_score": 110,
        "away_fga": 82, "home_fga": 98,
    },
    {
        "name": "2026_regular_gsw_det",
        "url": "https://statsdmz.nba.com/pdfs/20260320/20260320_GSWDET_book.pdf",
        "away": "Golden State Warriors", "home": "Detroit Pistons",
        "away_score": 101, "home_score": 115,
        "away_fga": 76, "home_fga": 86,
    },
    {
        "name": "2026_regular_lal_orl",
        "url": "https://statsdmz.nba.com/pdfs/20260321/20260321_LALORL_book.pdf",
        "away": "Los Angeles Lakers", "home": "Orlando Magic",
        "away_score": 105, "home_score": 104,
        "away_fga": 87, "home_fga": 83,
    },
)
MEDIA_CENTRAL_URL = "https://www.nba.com/stats/tools/media-central-game-stats"

GAMEBOOK_MARKERS = (
    "NATIONAL BASKETBALL ASSOCIATION OFFICIAL SCORER'S",
    "FINAL BOX",
    "SCORE BY",
)
REPORT_TERMS = (
    "Latest Boxscore Lines",
    "Game-by-Game",
    "Overall Statistics",
    "Offensive/Defensive",
    "Media Central Game Stats",
    "Provided by Elias",
)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
ATTR_URL_RE = re.compile(
    r'(?:src|href|data-[a-z0-9_-]*(?:url|src|endpoint))=["\']([^"\']+)["\']',
    re.I,
)
ABS_URL_RE = re.compile(r'https?://[^"\'<>\\\s]+', re.I)
SCRIPT_RE = re.compile(
    r'<script[^>]+(?:id=["\']([^"\']*)["\'])?[^>]*src=["\']([^"\']+)["\']',
    re.I,
)
INJURY_STRUCTURE_MARKERS = (
    "Injury-Report_",
    "ak-static.cms.nba.com",
    "referee/injury",
    "wp-json",
    "admin-ajax",
    "ajaxurl",
    "iframe",
)


def _gamebook_probe(data: bytes, expected: dict[str, Any]) -> dict[str, Any]:
    if not data.startswith(b"%PDF"):
        raise ValueError("official gamebook response is not a PDF")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf is required for gamebook diagnostics") from None
    reader = PdfReader(BytesIO(data))
    if not reader.pages:
        raise ValueError("official gamebook PDF has no pages")
    # First page contains final box/team totals. Parse two pages as a small
    # structural check without persisting document text.
    text = "\n".join((page.extract_text() or "") for page in reader.pages[:2])
    marker_hits = {
        marker: marker.casefold() in text.casefold()
        for marker in GAMEBOOK_MARKERS
    }
    stat_header = all(token in text for token in (
        "MIN", "FG", "FGA", "3P", "3PA", "FT", "FTA", "OR", "DR", "TOT", "TO", "PTS"
    ))
    team_total_lines = len(re.findall(
        r"240:00\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+",
        text,
    ))
    parsed = parse_gamebook_pdf(
        data,
        expected_away=str(expected["away"]),
        expected_home=str(expected["home"]),
    )
    exact_known_final = (
        parsed["away_score"] == int(expected["away_score"])
        and parsed["home_score"] == int(expected["home_score"])
        and parsed["away"]["totals"]["FGA"] == int(expected["away_fga"])
        and parsed["home"]["totals"]["FGA"] == int(expected["home_fga"])
    )
    return {
        # Team identity is validated by parse_gamebook_pdf against the expected
        # schedule names. Do not depend on PDF text capitalization/spacing for
        # that same assertion: pypdf layout extraction legitimately varies.
        "ok": (
            all(marker_hits.values())
            and stat_header
            and team_total_lines >= 2
            and exact_known_final
        ),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "pages": len(reader.pages),
        "marker_hits": marker_hits,
        "stat_header_signal": stat_header,
        "team_total_line_count": team_total_lines,
        "exact_known_final": exact_known_final,
        "parsed_scores": {
            "away": parsed["away_score"],
            "home": parsed["home_score"],
        },
        "parsed_player_counts": {
            "away": len(parsed["away"]["players"]),
            "home": len(parsed["home"]["players"]),
        },
        "raw_text_persisted": False,
    }


def _media_probe(html: str) -> dict[str, Any]:
    encoded = html.encode("utf-8")
    term_hits = {term: term in html for term in REPORT_TERMS}
    hrefs = HREF_RE.findall(html)
    safe_report_hints = sorted({
        href.split("?", 1)[0]
        for href in hrefs
        if any(token in href.lower() for token in (
            "pdf", "report", "stats", "gamebook", "boxscore", "media"
        ))
        and not any(secret in href.lower() for secret in ("token=", "key=", "auth="))
    })[:80]
    return {
        "ok": bool(term_hits["Media Central Game Stats"]),
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "term_hits": term_hits,
        "report_link_hints": safe_report_hints,
        "raw_html_persisted": False,
    }


def _previous_season(season: str) -> str:
    start = int(season[:4]) - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _safe_url_hint(value: str, base_host: str = "official.nba.com") -> str | None:
    clean = (
        str(value)
        .replace("\\/", "/")
        .replace("&amp;", "&")
        .strip()
    )
    if not clean:
        return None
    if clean.startswith("//"):
        clean = "https:" + clean
    if clean.startswith("/"):
        clean = f"https://{base_host}{clean}"
    if not clean.startswith(("http://", "https://")):
        return None
    parsed = urlsplit(clean)
    host = (parsed.hostname or "").lower()
    if not (
        host == "official.nba.com"
        or host.endswith(".nba.com")
        or host.endswith(".cms.nba.com")
    ):
        return None
    # Diagnostics retain only scheme/host/path to avoid persisting query
    # tokens, nonces or other transient parameters.
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _injury_page_probe(html: str, *, season: str) -> dict[str, Any]:
    normalized = str(html).replace("\\/", "/")
    encoded = normalized.encode("utf-8")
    marker_counts = {
        marker: normalized.casefold().count(marker.casefold())
        for marker in INJURY_STRUCTURE_MARKERS
    }
    hints: set[str] = set()
    for candidate in (
        list(ATTR_URL_RE.findall(normalized))
        + list(ABS_URL_RE.findall(normalized))
    ):
        safe = _safe_url_hint(candidate)
        if safe and any(
            token in safe.lower()
            for token in ("injury", "report", "ajax", "api", "json", "referee")
        ):
            hints.add(safe)
    scripts = []
    for script_id, src in SCRIPT_RE.findall(normalized):
        safe = _safe_url_hint(src)
        if safe is not None:
            scripts.append({
                "id": script_id or None,
                "src": safe,
            })
    return {
        "ok": len(normalized) > 1000,
        "season": season,
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "marker_counts": marker_counts,
        "safe_endpoint_hints": sorted(hints)[:100],
        "script_sources": scripts[:80],
        "raw_html_persisted": False,
    }


def run() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    current_season = season_for_date(now)
    historical_season = _previous_season(current_season)
    gamebooks: dict[str, Any] = {}
    media: dict[str, Any]
    injury_page: dict[str, Any]
    for expected in KNOWN_GAMEBOOKS:
        name = str(expected["name"])
        try:
            data = get_bytes(
                str(expected["url"]),
                headers={"Accept": "application/pdf"},
                timeout=15.0,
                retries=0,
            )
            gamebooks[name] = _gamebook_probe(data, expected)
        except Exception as exc:
            gamebooks[name] = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
    try:
        html = get_text(
            MEDIA_CENTRAL_URL,
            headers={"Accept": "text/html,*/*"},
            timeout=12.0,
            retries=0,
        )
        media = _media_probe(html)
    except Exception as exc:
        media = {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    try:
        injury_html = get_text(
            injury_page_url(historical_season),
            headers={"Accept": "text/html,*/*"},
            timeout=12.0,
            retries=0,
        )
        injury_page = _injury_page_probe(
            injury_html, season=historical_season
        )
    except Exception as exc:
        injury_page = {
            "ok": False,
            "season": historical_season,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "raw_html_persisted": False,
        }
    candidate = bool(gamebooks) and all(
        row.get("ok") is True for row in gamebooks.values()
    )
    return {
        "schema": "pulsar-nba-official-report-probe-v1",
        "checked_at": now.isoformat(),
        "role": "NETWORK_DIAGNOSTIC_ONLY",
        "predictive_evidence_eligible": False,
        "production_provider_authorized": False,
        "odds_api_requests": 0,
        "official_gamebook_candidate": candidate,
        "media_central_reachable": bool(media.get("ok")),
        "gamebook_samples": gamebooks,
        "gamebook_samples_ok": sum(
            row.get("ok") is True for row in gamebooks.values()
        ),
        "gamebook_samples_total": len(gamebooks),
        "media_central": media,
        "historical_injury_page": injury_page,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe official NBA gamebook and Media Central report surfaces"
    )
    parser.add_argument("--output", default="runtime/official_report_probe.json")
    args = parser.parse_args()
    result = run()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
