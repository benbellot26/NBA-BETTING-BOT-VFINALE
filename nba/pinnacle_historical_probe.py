"""Historical Pinnacle availability diagnostic for one NBA snapshot.

This is manual diagnostic evidence only. It helps distinguish current market
absence from account/provider inability to return Pinnacle.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .acquisition import (
    NBA_REGULAR_SPORT_KEY,
    VALID_NBA_ODDS_SPORT_KEYS,
    fetch_historical_nba_odds_diagnostic,
)
from .market import paired_price_rows
from .odds_budget import reserve as reserve_odds_request
from .odds_normalizer import normalize_game


def _coverage(events: list[dict[str, Any]]) -> dict[str, Any]:
    paired = {"ML": 0, "SPREAD": 0, "TOTAL": 0}
    complete = 0
    pin_events = 0
    for raw in events:
        event = normalize_game(raw)
        found: set[str] = set()
        any_pin = False
        for market, left, right in (
            ("ML", "HOME", "AWAY"),
            ("SPREAD", "HOME", "AWAY"),
            ("TOTAL", "OVER", "UNDER"),
        ):
            for book in event["markets"][market]:
                if str(book.get("bookmaker") or "").lower() != "pinnacle":
                    continue
                any_pin = any_pin or bool(book.get("selections"))
                points = [None] if market == "ML" else [
                    row.get("point")
                    for row in book.get("selections") or []
                    if row.get("selection") == left and row.get("point") is not None
                ]
                if any(
                    paired_price_rows(book, left, right, point=point) is not None
                    for point in points
                ):
                    paired[market] += 1
                    found.add(market)
                    break
        pin_events += int(any_pin)
        complete += int(len(found) == 3)
    return {
        "events": len(events),
        "pinnacle_events": pin_events,
        "paired_pinnacle_market_events": paired,
        "complete_pinnacle_events": complete,
    }


def run(
    *,
    date_iso: str,
    sport_key: str = NBA_REGULAR_SPORT_KEY,
    budget_path: str = "runtime/odds_budget.json",
) -> dict[str, Any]:
    if sport_key not in VALID_NBA_ODDS_SPORT_KEYS:
        raise ValueError(f"unsupported sport key {sport_key}")
    parsed = datetime.fromisoformat(str(date_iso).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("historical probe date requires timezone")
    if parsed.astimezone(timezone.utc) >= datetime.now(timezone.utc):
        raise ValueError("historical probe date must be in the past")

    reserve_odds_request(path=budget_path, purpose=f"pinnacle_historical_probe:{sport_key}")
    payload = fetch_historical_nba_odds_diagnostic(
        date_iso=date_iso,
        bookmakers="pinnacle",
        sport_key=sport_key,
    )
    coverage = _coverage(list(payload["data"]))
    if coverage["complete_pinnacle_events"] > 0:
        state = "HISTORICAL_PINNACLE_READY"
    elif coverage["pinnacle_events"] > 0:
        state = "HISTORICAL_PINNACLE_PARTIAL"
    elif coverage["events"] > 0:
        state = "HISTORICAL_PINNACLE_ABSENT"
    else:
        state = "HISTORICAL_NO_EVENTS"

    return {
        "schema": "pulsar-nba-pinnacle-historical-probe-v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "requested_snapshot_at": parsed.astimezone(timezone.utc).isoformat(),
        "role": "MARKET_DIAGNOSTIC_ONLY",
        "sport_key": sport_key,
        "state": state,
        "request_count": 1,
        **coverage,
        "provider_timestamp": payload.get("timestamp"),
        "previous_timestamp": payload.get("previous_timestamp"),
        "next_timestamp": payload.get("next_timestamp"),
        "quota": payload.get("usage") or {},
        "benchmark_bookmaker": "pinnacle",
        "pinnacle_replacement_allowed": False,
        "production_market_authorized": False,
        "betting_certified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Historical Pinnacle NBA probe")
    parser.add_argument("--date", required=True)
    parser.add_argument(
        "--sport-key",
        choices=sorted(VALID_NBA_ODDS_SPORT_KEYS),
        default=NBA_REGULAR_SPORT_KEY,
    )
    parser.add_argument("--budget", default="runtime/odds_budget.json")
    parser.add_argument("--output", default="runtime/pinnacle_historical_probe.json")
    args = parser.parse_args()
    result = run(
        date_iso=args.date,
        sport_key=args.sport_key,
        budget_path=args.budget,
    )
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
