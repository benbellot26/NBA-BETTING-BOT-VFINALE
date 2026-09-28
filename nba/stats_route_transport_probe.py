"""Transport-only probe for candidate official NBA stats backend routes.

This module never authorizes a provider. It sends the same minimal
LeagueDashTeamStats query to a small allowlisted set of official NBA hosts and
records only status/category/size/hash metadata.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import urlencode

from .nba_stats_api import _common, _result_rows
from .provider_http import ProviderError, get_bytes

ROLE = "NETWORK_DIAGNOSTIC_ONLY"

CANDIDATES = (
    ("stats_primary", "https://stats.nba.com/stats/leaguedashteamstats"),
    ("api_hub_stats_path", "https://api-hub.nba.com/stats/leaguedashteamstats"),
    ("api_hub_direct", "https://api-hub.nba.com/leaguedashteamstats"),
)


def _classify_error(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "timeout" in lowered:
        return "TIMEOUT"
    for code in (401, 403, 404, 405, 429, 451, 461):
        if f"http {code}" in lowered:
            return f"HTTP_{code}"
    return "UNAVAILABLE"


def _probe(name: str, base: str, *, season: str, timeout: float) -> dict[str, Any]:
    params = _common(season, 0, "Advanced")
    url = f"{base}?{urlencode(params)}"
    started = monotonic()
    try:
        data = get_bytes(url, timeout=timeout, retries=0)
        elapsed = round((monotonic() - started) * 1000.0, 1)
        digest = hashlib.sha256(data).hexdigest()
        try:
            payload = json.loads(data.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {
                "name": name,
                "endpoint": base,
                "state": "NON_JSON_RESPONSE",
                "ok": False,
                "elapsed_ms": elapsed,
                "bytes": len(data),
                "sha256": digest,
            }
        if not isinstance(payload, dict):
            return {
                "name": name,
                "endpoint": base,
                "state": "JSON_NON_OBJECT",
                "ok": False,
                "elapsed_ms": elapsed,
                "bytes": len(data),
                "sha256": digest,
            }
        try:
            rows = _result_rows(payload)
        except Exception:
            return {
                "name": name,
                "endpoint": base,
                "state": "JSON_NON_STATS_PAYLOAD",
                "ok": False,
                "elapsed_ms": elapsed,
                "bytes": len(data),
                "sha256": digest,
                "top_level_keys": sorted(str(key) for key in payload)[:20],
            }
        return {
            "name": name,
            "endpoint": base,
            "state": "VALID_STATS_PAYLOAD" if len(rows) >= 25 else "STATS_PAYLOAD_TOO_SMALL",
            "ok": len(rows) >= 25,
            "elapsed_ms": elapsed,
            "bytes": len(data),
            "sha256": digest,
            "rows": len(rows),
        }
    except ProviderError as exc:
        elapsed = round((monotonic() - started) * 1000.0, 1)
        return {
            "name": name,
            "endpoint": base,
            "state": _classify_error(exc),
            "ok": False,
            "elapsed_ms": elapsed,
            "error": str(exc),
        }


def run(*, season: str = "2025-26", timeout: float = 8.0) -> dict[str, Any]:
    if timeout <= 0 or timeout > 20:
        raise ValueError("timeout must be in (0,20]")
    rows = [
        _probe(name, endpoint, season=season, timeout=timeout)
        for name, endpoint in CANDIDATES
    ]
    valid = [row for row in rows if row.get("state") == "VALID_STATS_PAYLOAD"]
    return {
        "schema": "pulsar-nba-stats-route-transport-v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "role": ROLE,
        "season": season,
        "candidate_count": len(rows),
        "valid_stats_routes": [row["name"] for row in valid],
        "alternate_official_route_found": any(
            row["name"] != "stats_primary" for row in valid
        ),
        "predictive_evidence_eligible": False,
        "production_provider_authorized": False,
        "odds_api_requests": 0,
        "routes": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe official NBA stats route transport")
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--output", default="runtime/stats_route_transport_probe.json")
    args = parser.parse_args()
    result = run(season=args.season, timeout=args.timeout)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
