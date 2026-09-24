from __future__ import annotations
from datetime import datetime, timezone
import argparse
from pathlib import Path
import json
from typing import Any

from .injury_pdf import fetch_latest_report
from .nba_stats_api import team_stats
from .schedule import fetch_schedule, season_for_date

HARD_FAILURE_STATES = {"ACCESS_BLOCKED", "TIMEOUT", "UNAVAILABLE"}


def _previous(season: str) -> str:
    start = int(season[:4]) - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _classify_failure(exc: Exception) -> str:
    message = str(exc).lower()
    if "http 401" in message or "http 403" in message:
        return "ACCESS_BLOCKED"
    if "timeout" in message:
        return "TIMEOUT"
    if "no timestamped pdf report" in message:
        return "NOT_PUBLISHED"
    return "UNAVAILABLE"


def _provider_row(*, state: str, operational_ready: bool,
                  reachable: bool | None = None, **extra: Any) -> dict[str, Any]:
    row = {
        "state": state,
        "operational_ready": bool(operational_ready),
    }
    if reachable is not None:
        row["reachable"] = bool(reachable)
    row.update(extra)
    return row


def run() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    season = season_for_date(now)
    providers: dict[str, dict[str, Any]] = {}

    try:
        games = fetch_schedule()
        if len(games) < 1000:
            raise RuntimeError(f"unexpected schedule size {len(games)}")
        providers["schedule"] = _provider_row(
            state="OK", operational_ready=True, reachable=True, games=len(games))
    except Exception as exc:
        state = _classify_failure(exc)
        providers["schedule"] = _provider_row(
            state=state, operational_ready=False,
            reachable=False if state in HARD_FAILURE_STATES else None,
            error=str(exc))

    stats_season = season
    try:
        rows = team_stats(season=stats_season, last_n_games=0, measure_type="Advanced")
        if len(rows) >= 25:
            providers["stats"] = _provider_row(
                state="OK", operational_ready=True, reachable=True,
                season=stats_season, teams=len(rows))
        else:
            previous = _previous(season)
            historical = team_stats(
                season=previous, last_n_games=0, measure_type="Advanced")
            if len(historical) < 25:
                raise RuntimeError(
                    f"unexpected team-stat row count current={len(rows)} historical={len(historical)}")
            providers["stats"] = _provider_row(
                state="HISTORICAL_ONLY", operational_ready=False, reachable=True,
                season=season, current_teams=len(rows),
                probe_season=previous, probe_teams=len(historical))
    except Exception as exc:
        state = _classify_failure(exc)
        providers["stats"] = _provider_row(
            state=state, operational_ready=False,
            reachable=False if state in HARD_FAILURE_STATES else None,
            error=str(exc))

    try:
        report = fetch_latest_report(season=season)
        if not report.get("team_status"):
            raise RuntimeError("injury report parsed no team submission state")
        providers["injuries"] = _provider_row(
            state="OK", operational_ready=True, reachable=True,
            season=season, records=int(report.get("record_count") or 0),
            teams=len(report.get("team_status") or {}),
            reported_at=report["reported_at"])
    except Exception as exc:
        state = _classify_failure(exc)
        row = _provider_row(
            state=state, operational_ready=False,
            reachable=(True if state == "NOT_PUBLISHED"
                       else False if state in HARD_FAILURE_STATES else None),
            season=season, error=str(exc))
        if state == "NOT_PUBLISHED":
            # Probe the previous season only to distinguish parser/transport
            # health from "no current report yet". Historical data never makes
            # current-season acquisition operational.
            previous = _previous(season)
            try:
                prior = fetch_latest_report(season=previous)
                row["historical_probe"] = {
                    "ok": bool(prior.get("team_status")),
                    "season": previous,
                    "records": int(prior.get("record_count") or 0),
                }
            except Exception as probe_exc:
                row["historical_probe"] = {
                    "ok": False, "season": previous,
                    "state": _classify_failure(probe_exc),
                }
        providers["injuries"] = row

    states = {name: row["state"] for name, row in providers.items()}
    operational_ready = all(row["operational_ready"] for row in providers.values())
    hard = any(state in HARD_FAILURE_STATES for state in states.values())
    waiting = any(state in {"NOT_PUBLISHED", "HISTORICAL_ONLY"} for state in states.values())
    overall_state = (
        "READY" if operational_ready
        else "BLOCKED" if hard
        else "WAITING_FOR_PUBLICATION" if waiting
        else "DEGRADED"
    )
    transport_ok = not hard
    return {
        "schema": "pulsar-nba-provider-smoke-v2",
        "checked_at": now.isoformat(),
        "season": season,
        "state": overall_state,
        "transport_ok": transport_ok,
        "operational_ready": operational_ready,
        "ok": operational_ready,
        "providers": providers,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    result = run()
    payload = json.dumps(result, indent=2)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
    print(payload)
    if not result["operational_ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
