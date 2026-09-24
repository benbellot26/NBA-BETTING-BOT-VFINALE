"""Network-only diagnostics for the runner used by NBA acquisition.

No Odds API key is read and no result from this module is predictive evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from time import monotonic
from typing import Any, Callable

from .injury_pdf import injury_page_url
from .nba_stats_api import team_stats
from .provider_http import get_json, get_text
from .provider_smoke import _classify_failure, _previous
from .schedule import DEFAULT_SCHEDULE_URL, season_for_date


def _timed(name: str, source: str, call: Callable[[], Any]) -> dict[str, Any]:
    started = monotonic()
    try:
        value = call()
        elapsed = round((monotonic() - started) * 1000.0, 1)
        size = len(value) if hasattr(value, "__len__") else None
        return {"name": name, "ok": True, "state": "REACHABLE",
                "elapsed_ms": elapsed, "size": size}
    except Exception as exc:
        elapsed = round((monotonic() - started) * 1000.0, 1)
        return {"name": name, "ok": False,
                "state": _classify_failure(exc, source=source),
                "elapsed_ms": elapsed, "error": str(exc)}


def run() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    season = season_for_date(now)
    previous = _previous(season)
    probes = {
        "cdn_schedule_json": _timed(
            "cdn_schedule_json", "schedule",
            lambda: get_json(DEFAULT_SCHEDULE_URL, timeout=10.0, retries=0)),
        "api_hub_schedule_page": _timed(
            "api_hub_schedule_page", "schedule",
            lambda: get_text("https://api-hub.nba.com/schedule",
                             timeout=10.0, retries=0)),
        "nba_pr_schedule_release": _timed(
            "nba_pr_schedule_release", "schedule",
            lambda: get_text(
                f"https://pr.nba.com/{season}-nba-regular-season-schedule",
                timeout=10.0, retries=0)),
        "www_nba_stats_page": _timed(
            "www_nba_stats_page", "stats",
            lambda: get_text(f"https://www.nba.com/stats/teams/advanced?Season={previous}",
                             timeout=10.0, retries=0)),
        "official_injury_page": _timed(
            "official_injury_page", "injuries",
            lambda: get_text(injury_page_url(season),
                             timeout=10.0, retries=0)),
        "historical_stats_api": _timed(
            "historical_stats_api", "stats",
            lambda: team_stats(
                season=previous, last_n_games=0, measure_type="Advanced",
                timeout=10.0, retries=0)),
    }
    reachable = [name for name, row in probes.items() if row["ok"]]
    return {
        "schema": "pulsar-nba-runner-network-probe-v1",
        "checked_at": now.isoformat(),
        "season": season,
        "probe_season": previous,
        "role": "NETWORK_DIAGNOSTIC_ONLY",
        "predictive_evidence_eligible": False,
        "odds_api_requests": 0,
        "reachable_routes": reachable,
        "probes": probes,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="runtime/runner_probe.json")
    args = parser.parse_args()
    result = run()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
