"""REFERENCE_ONLY inspection of __NEXT_DATA__ on reachable NBA stats pages.

No raw HTML, player rows or team rows are persisted. This diagnostic can only
describe structure and sanitized endpoint hints; it never becomes a production
provider automatically.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html as html_lib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .provider_http import get_text
from .provider_smoke import _previous
from .schedule import season_for_date
from .snapshot_store import canonical_bytes

SCRIPT_RE = re.compile(
    r"<script[^>]*id=[\"']__NEXT_DATA__[\"'][^>]*>(.*?)</script>",
    re.I | re.S,
)
INTERESTING_TOKENS = (
    "stat", "team", "player", "league", "season", "game", "result", "endpoint",
)
BASKETBALL_KEYS = {
    "off_rating", "def_rating", "pace", "team_name", "player_name",
    "team_id", "player_id", "gp", "min",
}


def extract_next_data(page: str) -> Any:
    match = SCRIPT_RE.search(page)
    if match is None:
        raise ValueError("__NEXT_DATA__ script not found")
    try:
        return json.loads(html_lib.unescape(match.group(1)).strip())
    except json.JSONDecodeError:
        raise ValueError("__NEXT_DATA__ is not valid JSON") from None


def _safe_hint(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    if text.startswith(("http://", "https://")):
        parsed = urlsplit(text)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    if text.startswith("/") and any(token in text.lower() for token in (
        "/api/", "/stats/", "/graphql", "/data/",
    )):
        return text.split("?", 1)[0]
    return None


def analyze_payload(payload: Any) -> dict[str, Any]:
    node_count = 0
    max_depth = 0
    key_names: set[str] = set()
    interesting_paths: set[str] = set()
    large_arrays: list[dict[str, Any]] = []
    endpoint_hints: set[str] = set()

    def walk(value: Any, path: str, depth: int) -> None:
        nonlocal node_count, max_depth
        node_count += 1
        max_depth = max(max_depth, depth)
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key)
                key_names.add(key_text.casefold())
                child_path = f"{path}.{key_text}" if path else key_text
                if any(token in key_text.casefold() for token in INTERESTING_TOKENS):
                    interesting_paths.add(child_path)
                walk(child, child_path, depth + 1)
        elif isinstance(value, list):
            if len(value) >= 10:
                large_arrays.append({"path": path or "$", "length": len(value)})
            for index, child in enumerate(value[:100]):
                walk(child, f"{path}[{index}]", depth + 1)
        elif isinstance(value, str):
            hint = _safe_hint(value)
            if hint:
                endpoint_hints.add(hint)

    walk(payload, "", 0)
    normalized_keys = {
        re.sub(r"[^a-z0-9]+", "_", key).strip("_")
        for key in key_names
    }
    basketball_key_hits = sorted(BASKETBALL_KEYS & normalized_keys)
    candidate_arrays = [
        row for row in large_arrays
        if any(token in row["path"].casefold() for token in ("team", "player", "stat", "result"))
    ]
    return {
        "node_count": node_count,
        "max_depth": max_depth,
        "top_level_type": type(payload).__name__,
        "top_level_keys": sorted(payload.keys())[:50] if isinstance(payload, dict) else [],
        "interesting_paths": sorted(interesting_paths)[:100],
        "large_arrays": sorted(large_arrays, key=lambda row: (-row["length"], row["path"]))[:50],
        "candidate_data_arrays": sorted(candidate_arrays, key=lambda row: (-row["length"], row["path"]))[:30],
        "basketball_key_hits": basketball_key_hits,
        "endpoint_hints": sorted(endpoint_hints)[:50],
        "reference_data_candidate": bool(candidate_arrays and basketball_key_hits),
    }


def run(*, season: str | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    probe_season = season or _previous(season_for_date(now))
    urls = {
        "teams_advanced": f"https://www.nba.com/stats/teams/advanced?Season={probe_season}&SeasonType=Regular%20Season",
        "teams_traditional": f"https://www.nba.com/stats/teams/traditional?Season={probe_season}&SeasonType=Regular%20Season",
        "players_advanced": f"https://www.nba.com/stats/players/advanced?Season={probe_season}&SeasonType=Regular%20Season",
        "players_traditional": f"https://www.nba.com/stats/players/traditional?Season={probe_season}&SeasonType=Regular%20Season",
    }
    pages: dict[str, Any] = {}
    for name, url in urls.items():
        try:
            page = get_text(
                url, headers={"Accept": "text/html,*/*"},
                timeout=12.0, retries=0)
            payload = extract_next_data(page)
            analysis = analyze_payload(payload)
            pages[name] = {
                "ok": True,
                "next_data_sha256": hashlib.sha256(canonical_bytes(payload)).hexdigest(),
                **analysis,
            }
        except Exception as exc:
            pages[name] = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
    candidates = [
        name for name, row in pages.items()
        if row.get("reference_data_candidate") is True
    ]
    endpoint_hints = sorted({
        hint
        for row in pages.values()
        for hint in (row.get("endpoint_hints") or [])
    })
    return {
        "schema": "pulsar-nba-nextdata-reference-probe-v1",
        "checked_at": now.isoformat(),
        "season": probe_season,
        "role": "REFERENCE_ONLY",
        "predictive_evidence_eligible": False,
        "production_provider_authorized": False,
        "odds_api_requests": 0,
        "reference_candidate_pages": candidates,
        "sanitized_endpoint_hints": endpoint_hints[:100],
        "pages": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season")
    parser.add_argument(
        "--output", default="runtime/www_nextdata_probe.json")
    args = parser.parse_args()
    result = run(season=args.season)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
