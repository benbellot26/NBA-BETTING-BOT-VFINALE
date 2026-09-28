"""Deep Pinnacle transport diagnostic.

This module is diagnostic-only. It compares the targeted bookmaker query with
the EU-region query for the same NBA sport key. It never replaces Pinnacle with
another bookmaker and never alters betting certification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .acquisition import (
    NBA_PRESEASON_SPORT_KEY,
    NBA_REGULAR_SPORT_KEY,
    VALID_NBA_ODDS_SPORT_KEYS,
    fetch_nba_odds_diagnostic,
)
from .market import fresh_quote, paired_price_rows
from .odds_budget import reserve as reserve_odds_request
from .odds_normalizer import normalize_game


def _raw_pinnacle(event: dict[str, Any]) -> bool:
    return any(
        str(book.get("key") or book.get("title") or "").strip().lower() == "pinnacle"
        for book in event.get("bookmakers") or []
    )


def _coverage(events: list[dict[str, Any]], *, checked_at: str) -> dict[str, Any]:
    normalized = [normalize_game(row) for row in events]
    paired = {"ML": 0, "SPREAD": 0, "TOTAL": 0}
    fresh = {"ML": 0, "SPREAD": 0, "TOTAL": 0}
    complete = 0
    pinnacle_events = 0
    for event in normalized:
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
                    if fresh_quote(book.get("last_update"), checked_at):
                        fresh[market] += 1
                    break
        pinnacle_events += int(any_pin)
        complete += int(len(found) == 3)
    return {
        "events": len(events),
        "raw_events_with_bookmakers": sum(bool(row.get("bookmakers")) for row in events),
        "raw_events_with_pinnacle": sum(_raw_pinnacle(row) for row in events),
        "normalized_pinnacle_events": pinnacle_events,
        "paired_pinnacle_market_events": paired,
        "fresh_pinnacle_market_events": fresh,
        "complete_pinnacle_events": complete,
        "event_ids": sorted(str(row.get("id") or "") for row in events if row.get("id")),
    }


def run(
    *,
    sport_key: str = NBA_REGULAR_SPORT_KEY,
    budget_path: str = "runtime/odds_budget.json",
) -> dict[str, Any]:
    if sport_key not in VALID_NBA_ODDS_SPORT_KEYS:
        raise ValueError(f"unsupported sport key {sport_key}")
    checked_at = datetime.now(timezone.utc).isoformat()

    reserve_odds_request(path=budget_path, purpose=f"pinnacle_target_probe:{sport_key}")
    targeted = fetch_nba_odds_diagnostic(
        bookmakers="pinnacle", sport_key=sport_key
    )
    reserve_odds_request(path=budget_path, purpose=f"pinnacle_eu_probe:{sport_key}")
    regional = fetch_nba_odds_diagnostic(
        bookmakers=None, regions="eu", sport_key=sport_key
    )

    target_cov = _coverage(list(targeted["events"]), checked_at=checked_at)
    region_cov = _coverage(list(regional["events"]), checked_at=checked_at)
    target_ids = set(target_cov["event_ids"])
    region_ids = set(region_cov["event_ids"])

    if target_cov["complete_pinnacle_events"] > 0:
        state = "TARGETED_PINNACLE_READY"
    elif target_cov["normalized_pinnacle_events"] > 0:
        state = "TARGETED_PINNACLE_PARTIAL"
    elif region_cov["raw_events_with_pinnacle"] > 0:
        state = "TARGET_FILTER_MISMATCH"
    elif target_cov["events"] == 0 and region_cov["events"] == 0:
        state = "NO_EVENTS_FOR_SPORT_KEY"
    elif region_cov["events"] > 0:
        state = "PINNACLE_NOT_CURRENTLY_LISTED"
    else:
        state = "REGIONAL_MARKET_EMPTY"

    return {
        "schema": "pulsar-nba-pinnacle-transport-probe-v1",
        "checked_at": checked_at,
        "role": "MARKET_DIAGNOSTIC_ONLY",
        "sport_key": sport_key,
        "season_mode": (
            "PRESEASON"
            if sport_key == NBA_PRESEASON_SPORT_KEY
            else "REGULAR"
        ),
        "state": state,
        "request_count": 2,
        "targeted": target_cov,
        "eu_region": region_cov,
        "common_event_ids": len(target_ids & region_ids),
        "target_only_event_ids": len(target_ids - region_ids),
        "region_only_event_ids": len(region_ids - target_ids),
        "targeted_quota": targeted.get("usage") or {},
        "regional_quota": regional.get("usage") or {},
        "benchmark_bookmaker": "pinnacle",
        "pinnacle_replacement_allowed": False,
        "production_market_authorized": False,
        "betting_certified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Deep current Pinnacle transport probe")
    parser.add_argument(
        "--sport-key",
        choices=sorted(VALID_NBA_ODDS_SPORT_KEYS),
        default=NBA_REGULAR_SPORT_KEY,
    )
    parser.add_argument("--budget", default="runtime/odds_budget.json")
    parser.add_argument("--output", default="runtime/pinnacle_transport_probe.json")
    args = parser.parse_args()
    result = run(sport_key=args.sport_key, budget_path=args.budget)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
