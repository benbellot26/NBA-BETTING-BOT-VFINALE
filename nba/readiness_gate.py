"""Offline gate over already persisted real-provider diagnostics.

This module performs NO network calls and can never authorize betting.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def _dt(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("diagnostic timestamp lacks timezone")
    return parsed.astimezone(timezone.utc)


def _age_hours(value: Any, now: datetime) -> float:
    return (now - _dt(value)).total_seconds() / 3600.0


def assess(*, provider: dict[str, Any] | None,
           market: dict[str, Any] | None,
           at: str | None = None,
           max_age_hours: float = 24.0) -> dict[str, Any]:
    if max_age_hours <= 0:
        raise ValueError("max_age_hours must be positive")
    now = _dt(at) if at else datetime.now(timezone.utc)
    failures: list[str] = []
    warnings: list[str] = []
    ages: dict[str, float | None] = {"provider": None, "market": None}

    if not provider:
        failures.append("provider_smoke_missing")
    else:
        if provider.get("schema") != "pulsar-nba-provider-smoke-v2":
            failures.append("provider_smoke_schema_unsupported")
        try:
            ages["provider"] = _age_hours(provider["checked_at"], now)
            if ages["provider"] < -0.1:
                failures.append("provider_smoke_from_future")
            elif ages["provider"] > max_age_hours:
                failures.append(f"provider_smoke_stale>{max_age_hours:g}h")
        except (KeyError, TypeError, ValueError):
            failures.append("provider_smoke_timestamp_invalid")
        if provider.get("operational_ready") is not True:
            failures.append(
                f"provider_not_operational:{provider.get('state') or 'UNKNOWN'}")
            for name, row in (provider.get("providers") or {}).items():
                state = str((row or {}).get("state") or "UNKNOWN")
                if state != "OK":
                    warnings.append(f"provider:{name}:{state}")

    if not market:
        failures.append("market_smoke_missing")
    else:
        if market.get("schema") != "pulsar-nba-market-smoke-v2":
            failures.append("market_smoke_schema_unsupported")
        try:
            ages["market"] = _age_hours(market["checked_at"], now)
            if ages["market"] < -0.1:
                failures.append("market_smoke_from_future")
            elif ages["market"] > max_age_hours:
                failures.append(f"market_smoke_stale>{max_age_hours:g}h")
        except (KeyError, TypeError, ValueError):
            failures.append("market_smoke_timestamp_invalid")
        if market.get("coverage_ready") is not True:
            failures.append("pinnacle_market_coverage_not_ready")
        if int(market.get("complete_pinnacle_events") or 0) < 1:
            failures.append("no_complete_pinnacle_event")

    failures = list(dict.fromkeys(failures))
    return {
        "schema": "pulsar-nba-operational-readiness-v1",
        "role": "PRESEASON_OPERATIONAL_GATE_ONLY",
        "checked_at": now.isoformat(),
        "max_age_hours": max_age_hours,
        "diagnostic_age_hours": ages,
        "ready_for_real_rehearsal": not failures,
        "live_operational": False,
        "real_betting_authorized": False,
        "betting_certified": False,
        "failures": failures,
        "warnings": warnings,
    }


def _read(path: str | Path) -> dict[str, Any] | None:
    target = Path(path)
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline readiness gate over persisted provider/market diagnostics")
    parser.add_argument("--provider", default="runtime/provider_smoke.json")
    parser.add_argument("--market", default="runtime/market_smoke.json")
    parser.add_argument("--output", default="runtime/readiness_gate.json")
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    args = parser.parse_args()
    result = assess(
        provider=_read(args.provider), market=_read(args.market),
        max_age_hours=args.max_age_hours)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["ready_for_real_rehearsal"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
