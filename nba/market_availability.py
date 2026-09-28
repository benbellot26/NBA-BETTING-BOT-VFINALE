"""Persist compact Pinnacle availability history from market diagnostics."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .tracking import append_jsonl


def _read_json(path: str | Path) -> dict[str, Any] | None:
    target = Path(path)
    if not target.exists():
        return None
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def record(
    *,
    market_path: str = "runtime/market_smoke.json",
    discovery_path: str = "runtime/bookmaker_discovery.json",
    history_path: str = "runtime/market_availability.jsonl",
    summary_path: str = "runtime/market_availability_summary.json",
) -> dict[str, Any]:
    market = _read_json(market_path) or {}
    discovery = _read_json(discovery_path) or {}
    if market.get("schema") != "pulsar-nba-market-smoke-v2":
        raise ValueError("market smoke missing or unsupported")
    key = f"{market.get('checked_at')}|{market.get('availability_state')}"
    history = _read_jsonl(history_path)
    seen = {str(row.get("entry_key") or "") for row in history}
    row = {
        "schema": "pulsar-nba-market-availability-v1",
        "entry_key": key,
        "checked_at": market.get("checked_at"),
        "availability_state": market.get("availability_state"),
        "events": int(market.get("events") or 0),
        "pinnacle_events": int(market.get("pinnacle_events") or 0),
        "complete_pinnacle_events": int(market.get("complete_pinnacle_events") or 0),
        "raw_events_with_any_bookmaker": int(market.get("raw_events_with_any_bookmaker") or 0),
        "raw_events_with_pinnacle": int(market.get("raw_events_with_pinnacle") or 0),
        "discovery_checked_at": discovery.get("checked_at"),
        "discovery_events": int(discovery.get("events") or 0),
        "discovery_pinnacle_present": discovery.get("pinnacle_present"),
        "discovery_pinnacle_state": discovery.get("pinnacle_state"),
        "benchmark_bookmaker": "pinnacle",
        "replacement_allowed": False,
    }
    if key not in seen:
        append_jsonl(history_path, row)
        history.append(row)

    consecutive_absent = 0
    for item in reversed(history):
        if item.get("availability_state") in {
            "PINNACLE_ABSENT", "PINNACLE_TARGET_EMPTY", "PINNACLE_PARTIAL"
        }:
            consecutive_absent += 1
        else:
            break
    summary = {
        "schema": "pulsar-nba-market-availability-summary-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "observations": len(history),
        "latest_state": row["availability_state"],
        "consecutive_not_ready": consecutive_absent,
        "latest_targeted_events": row["events"],
        "latest_targeted_pinnacle_events": row["pinnacle_events"],
        "latest_discovery_pinnacle_present": row["discovery_pinnacle_present"],
        "benchmark_bookmaker": "pinnacle",
        "replacement_allowed": False,
        "betting_certified": False,
    }
    target = Path(summary_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="runtime/market_smoke.json")
    parser.add_argument("--discovery", default="runtime/bookmaker_discovery.json")
    parser.add_argument("--history", default="runtime/market_availability.jsonl")
    parser.add_argument("--summary", default="runtime/market_availability_summary.json")
    args = parser.parse_args()
    print(json.dumps(record(
        market_path=args.market,
        discovery_path=args.discovery,
        history_path=args.history,
        summary_path=args.summary,
    ), indent=2))


if __name__ == "__main__":
    main()
