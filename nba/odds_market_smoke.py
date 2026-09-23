"""Explicit current-NBA market coverage probe. May consume Odds API credits."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .acquisition import fetch_nba_odds_with_meta

REQUIRED_MARKETS = {"h2h", "spreads", "totals"}


def run() -> dict[str, Any]:
    rows, quota = fetch_nba_odds_with_meta(bookmakers="pinnacle")
    complete = 0
    events: list[dict[str, Any]] = []
    for game in rows:
        pinnacle = next((b for b in game.get("bookmakers") or []
                         if str(b.get("key") or "").lower() == "pinnacle"), None)
        markets = {str(m.get("key") or "") for m in (pinnacle or {}).get("markets") or []}
        ok = REQUIRED_MARKETS <= markets
        complete += int(ok)
        events.append({
            "id": str(game.get("id") or ""),
            "commence_time": game.get("commence_time"),
            "home": game.get("home_team"),
            "away": game.get("away_team"),
            "pinnacle_markets": sorted(markets),
            "complete_featured_markets": ok,
        })
    return {
        "schema": "pulsar-nba-odds-market-smoke-v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "provider": "the-odds-api",
        "bookmaker": "pinnacle",
        "event_count": len(rows),
        "complete_event_count": complete,
        "coverage_ok": bool(rows) and complete == len(rows),
        "quota": quota,
        "events": events,
        "betting_certified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Current NBA odds/Pinnacle smoke; this request may consume API credits")
    parser.add_argument("--output", default="runtime/health/odds_market_smoke.json")
    parser.add_argument("--soft", action="store_true")
    args = parser.parse_args()
    result = run()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "event_count": result["event_count"],
        "complete_event_count": result["complete_event_count"],
        "coverage_ok": result["coverage_ok"],
        "quota": result["quota"],
    }, indent=2))
    if not result["coverage_ok"] and not args.soft:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
