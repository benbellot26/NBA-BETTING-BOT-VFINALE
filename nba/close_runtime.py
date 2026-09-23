from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from .acquisition import fetch_historical_nba_odds, fetch_nba_odds
from .market import no_vig_pair, paired_price_rows, fresh_quote
from .odds_normalizer import normalize_game
from .teams import canonical_team
from .tracking import append_jsonl

PAIR = {
    "home_ml": ("HOME", "AWAY"), "away_ml": ("AWAY", "HOME"),
    "home_spread": ("HOME", "AWAY"), "away_spread": ("AWAY", "HOME"),
    "over": ("OVER", "UNDER"), "under": ("UNDER", "OVER"),
}


def _read(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    return [json.loads(row) for row in target.read_text(encoding="utf-8").splitlines() if row.strip()] if target.exists() else []


def _dt(value: str) -> datetime:
    date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("close timestamps need timezone")
    return date.astimezone(timezone.utc)


def _match(entry: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((
        game for game in events if canonical_team(game["home"]) == canonical_team(entry["home"])
        and canonical_team(game["away"]) == canonical_team(entry["away"])
        and _dt(game["commence_time"]) == _dt(entry["commence_time"])
    ), None)


def _close_row(entry: dict[str, Any], event: dict[str, Any],
               captured_at: str, source_mode: str) -> dict[str, Any]:
    left, right = PAIR[entry["selection"]]
    books = event["markets"][entry["market"]]
    pin = next((book for book in books if str(book.get("bookmaker") or "").lower() == "pinnacle"), None)
    if pin is None:
        raise ValueError("Pinnacle close missing")
    options = [row for row in pin.get("selections") or [] if row.get("selection") == left]
    pair = None
    # Prefer the exact entry contract for price CLV. If the exact line no
    # longer exists, retain a paired current line for line CLV only.
    entry_point = entry.get("line")
    if entry["market"] != "ML" and entry_point is not None:
        pair = paired_price_rows(pin, left, right, point=float(entry_point))
    if pair is None:
        for candidate in options:
            pair = paired_price_rows(pin, left, right, point=candidate.get("point"))
            if pair is not None:
                break
    if pair is None:
        raise ValueError("paired Pinnacle close at the same contract missing")
    left_row, right_row = pair
    close_probability, _ = no_vig_pair(float(left_row["price"]), float(right_row["price"]))
    close_point = left_row.get("point")
    entry_point = entry.get("line")
    comparable = (
        entry["market"] == "ML"
        or (close_point is not None and entry_point is not None
            and abs(float(close_point) - float(entry_point)) <= 1e-7)
    )
    line_clv = None
    if entry["market"] == "SPREAD" and close_point is not None and entry_point is not None:
        line_clv = float(entry_point) - float(close_point)
    elif entry["market"] == "TOTAL" and close_point is not None and entry_point is not None:
        line_clv = (float(close_point) - float(entry_point)
                    if entry["selection"] == "over" else float(entry_point) - float(close_point))
    return {
        "entry_key": entry["entry_key"], "game_id": entry["game_id"],
        "market": entry["market"], "selection": entry["selection"],
        "entry_line": entry_point, "close_line": close_point,
        "entry_price": entry["price"], "pinnacle_close_price": float(left_row["price"]),
        "pinnacle_close_no_vig_probability": close_probability,
        "price_clv_comparable": comparable,
        "clv_pp": 100 * (close_probability - 1 / float(entry["price"])) if comparable else None,
        "line_clv": line_clv, "captured_at": captured_at, "source_mode": source_mode,
    }


def capture(*, paper_path: str, close_path: str, mode: str = "live",
            live_window_minutes: float = 20.0) -> dict[str, Any]:
    entries = _read(paper_path)
    closed = {row.get("entry_key") for row in _read(close_path)}
    pending = [row for row in entries if row.get("entry_key") not in closed]
    now = datetime.now(timezone.utc)
    added = 0
    failures: list[str] = []
    if not pending:
        return {"added": 0, "pending": 0, "failures": []}
    live_events: list[dict[str, Any]] | None = None
    historical_cache: dict[str, Any] = {}
    if mode == "live":
        try:
            live_events = [normalize_game(row) for row in fetch_nba_odds(bookmakers="pinnacle")]
        except Exception as exc:
            return {"added": 0, "pending": len(pending), "failures": [f"live_odds:{exc}"]}
    for entry in pending:
        try:
            tip = _dt(entry["commence_time"])
            if mode == "live":
                minutes = (tip - now).total_seconds() / 60.0
                if not 0 <= minutes <= live_window_minutes:
                    continue
                event = _match(entry, live_events or [])
                captured = now.isoformat()
            else:
                if tip > now:
                    continue
                target = (tip - timedelta(minutes=1)).isoformat()
                if target not in historical_cache:
                    historical_cache[target] = fetch_historical_nba_odds(
                        date_iso=target, bookmakers="pinnacle")
                payload = historical_cache[target]
                event = _match(entry, [normalize_game(x) for x in payload["data"]])
                captured = str(payload.get("timestamp") or "")
                if not captured or _dt(captured) >= tip:
                    raise ValueError("historical close was not before tip")
            if event is None:
                raise ValueError("event not found in close snapshot")
            pinnacle = next((book for book in event["markets"][entry["market"]]
                                 if str(book.get("bookmaker") or "").lower() == "pinnacle"), None)
            if pinnacle is None or not fresh_quote(pinnacle.get("last_update"), captured, max_age_minutes=30):
                raise ValueError("Pinnacle close quote is stale or missing")
            append_jsonl(close_path, _close_row(entry, event, captured, mode))
            closed.add(entry["entry_key"])
            added += 1
        except Exception as exc:
            failures.append(f"{entry.get('entry_key')}:{exc}")
    return {"added": added, "pending": len(pending) - added, "failures": failures}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", default="runtime/evidence/paper_entries.jsonl")
    parser.add_argument("--close", default="runtime/evidence/close_ledger.jsonl")
    parser.add_argument("--mode", choices=("live", "historical"), default="live")
    args = parser.parse_args()
    print(json.dumps(capture(paper_path=args.paper, close_path=args.close, mode=args.mode), indent=2))


if __name__ == "__main__":
    main()
