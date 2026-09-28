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

from .provider_http import get_bytes, get_text

# Verified NBA Official Scorer's Report from the 2025-26 regular season.
# A fixed historical document makes runner diagnostics deterministic and avoids
# depending on today's slate or on a source that has not published yet.
KNOWN_GAMEBOOK_URL = (
    "https://statsdmz.nba.com/pdfs/20260320/"
    "20260320_GSWDET_book.pdf"
)
MEDIA_CENTRAL_URL = "https://www.nba.com/stats/tools/media-central-game-stats"

GAMEBOOK_MARKERS = (
    "NATIONAL BASKETBALL ASSOCIATION OFFICIAL SCORER'S",
    "FINAL BOX",
    "VISITOR: Golden State Warriors",
    "HOME: DETROIT PISTONS",
    "SCORE BY",
    "Warriors",
    "PISTONS",
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


def _gamebook_probe(data: bytes) -> dict[str, Any]:
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
    marker_hits = {marker: marker in text for marker in GAMEBOOK_MARKERS}
    stat_header = all(token in text for token in (
        "MIN", "FG", "FGA", "3P", "3PA", "FT", "FTA", "OR", "DR", "TOT", "TO", "PTS"
    ))
    team_total_lines = len(re.findall(
        r"240:00\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+",
        text,
    ))
    return {
        "ok": all(marker_hits.values()) and stat_header and team_total_lines >= 2,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "pages": len(reader.pages),
        "marker_hits": marker_hits,
        "stat_header_signal": stat_header,
        "team_total_line_count": team_total_lines,
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


def run() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    gamebook: dict[str, Any]
    media: dict[str, Any]
    try:
        data = get_bytes(
            KNOWN_GAMEBOOK_URL,
            headers={"Accept": "application/pdf"},
            timeout=15.0,
            retries=0,
        )
        gamebook = _gamebook_probe(data)
    except Exception as exc:
        gamebook = {
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
    candidate = bool(gamebook.get("ok"))
    return {
        "schema": "pulsar-nba-official-report-probe-v1",
        "checked_at": now.isoformat(),
        "role": "NETWORK_DIAGNOSTIC_ONLY",
        "predictive_evidence_eligible": False,
        "production_provider_authorized": False,
        "odds_api_requests": 0,
        "official_gamebook_candidate": candidate,
        "media_central_reachable": bool(media.get("ok")),
        "gamebook": gamebook,
        "media_central": media,
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
