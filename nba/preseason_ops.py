"""Fail-closed one-click preseason validation over real sources.

Order:
1) official-provider smoke (free)
2) current Pinnacle market smoke (paid, only if provider is operational)
3) offline readiness gate
4) real-source live_runtime in PRESEASON mode only

This module never authorizes betting and never writes prospective evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .live_runtime import run as live_run
from .market_smoke import run as market_run
from .provider_smoke import run as provider_run
from .readiness_gate import assess as readiness_assess


ProviderRunner = Callable[[], dict[str, Any]]
MarketRunner = Callable[..., dict[str, Any]]
LiveRunner = Callable[..., dict[str, Any]]


def _write(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run(
    *,
    target_date: str,
    output: str = "runtime/preseason_validation.json",
    provider_output: str = "runtime/provider_smoke.json",
    market_output: str = "runtime/market_smoke.json",
    live_output: str = "runtime/preseason_live_run.json",
    odds_budget_path: str = "runtime/odds_budget.json",
    snapshot_root: str = "runtime/preseason_snapshots",
    provider_runner: ProviderRunner = provider_run,
    market_runner: MarketRunner = market_run,
    live_runner: LiveRunner = live_run,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "pulsar-nba-preseason-validation-v1",
        "role": "PRESEASON_VALIDATION_ONLY",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "target_date": target_date,
        "status": "STARTED",
        "provider": None,
        "market": None,
        "readiness": None,
        "rehearsal": None,
        "odds_api_requests": 0,
        "prospective_evidence_eligible": False,
        "real_betting_authorized": False,
        "betting_certified": False,
        "failures": [],
    }

    try:
        provider = provider_runner()
    except Exception as exc:
        result["status"] = "PROVIDER_ERROR"
        result["failures"].append(f"provider:{type(exc).__name__}:{exc}")
        _write(output, result)
        return result
    result["provider"] = provider
    _write(provider_output, provider)

    if provider.get("operational_ready") is not True:
        result["status"] = "PROVIDER_BLOCKED"
        result["failures"].append(
            f"provider_not_operational:{provider.get('state') or 'UNKNOWN'}")
        _write(output, result)
        return result

    try:
        market = market_runner(
            require_events=False, budget_path=odds_budget_path)
        result["odds_api_requests"] += int(market.get("request_count") or 0)
    except Exception as exc:
        result["status"] = "MARKET_ERROR"
        result["failures"].append(f"market:{type(exc).__name__}:{exc}")
        _write(output, result)
        return result
    result["market"] = market
    _write(market_output, market)

    readiness = readiness_assess(
        provider=provider, market=market, max_age_hours=1.0)
    result["readiness"] = readiness
    if readiness.get("ready_for_real_rehearsal") is not True:
        result["status"] = "MARKET_NOT_READY"
        result["failures"].extend(readiness.get("failures") or [])
        _write(output, result)
        return result

    try:
        rehearsal = live_runner(
            target_date=target_date,
            output=live_output,
            snapshot_root=snapshot_root,
            odds_budget_path=odds_budget_path,
            operating_mode="preseason",
        )
        result["odds_api_requests"] += int(
            rehearsal.get("odds_api_requests") or 0)
    except Exception as exc:
        result["status"] = "REHEARSAL_ERROR"
        result["failures"].append(f"rehearsal:{type(exc).__name__}:{exc}")
        _write(output, result)
        return result

    result["rehearsal"] = {
        "status": rehearsal.get("status"),
        "games": len(rehearsal.get("games") or []),
        "paper_recording": rehearsal.get("paper_recording"),
        "final_forecasts": rehearsal.get("final_forecasts"),
        "failures": rehearsal.get("failures") or [],
    }
    if (rehearsal.get("paper_recording") or {}).get("added", 0) != 0:
        result["status"] = "SAFETY_VIOLATION"
        result["failures"].append("preseason_wrote_paper_evidence")
    elif (rehearsal.get("final_forecasts") or {}).get("added", 0) != 0:
        result["status"] = "SAFETY_VIOLATION"
        result["failures"].append("preseason_wrote_prospective_forecast")
    elif rehearsal.get("status") == "OK" and rehearsal.get("games"):
        result["status"] = "REHEARSAL_COMPLETE"
    else:
        result["status"] = "REHEARSAL_INCOMPLETE"
        result["failures"].extend(rehearsal.get("failures") or [])

    _write(output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="One-click fail-closed NBA preseason validation")
    parser.add_argument(
        "--date",
        default=datetime.now(ZoneInfo("America/New_York")).date().isoformat())
    parser.add_argument(
        "--output", default="runtime/preseason_validation.json")
    args = parser.parse_args()
    result = run(target_date=args.date, output=args.output)
    print(json.dumps(result, indent=2))
    if result["status"] != "REHEARSAL_COMPLETE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
