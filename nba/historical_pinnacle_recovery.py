"""Research-only historical Pinnacle entry benchmark recovery.

This module never mutates prospective forecasts. It queries the historical odds
provider at the original forecast timestamp, then writes a separate derived
ledger. Historical recovery is evaluation-only and cannot satisfy live betting
or certification requirements.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .acquisition import fetch_historical_nba_odds
from .market import fresh_quote, pinnacle_no_vig
from .odds_budget import reserve as reserve_odds_request
from .odds_normalizer import normalize_game
from .teams import canonical_team
from .tracking import append_jsonl

SCHEMA = "pulsar-nba-historical-pinnacle-entry-v1"
ROLE = "HISTORICAL_EVALUATION_ONLY"


def _read(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    return [
        json.loads(line)
        for line in target.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _dt(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("historical Pinnacle timestamps require timezone")
    return parsed.astimezone(timezone.utc)


def _same_tip(a: str, b: str) -> bool:
    return abs((_dt(a) - _dt(b)).total_seconds()) <= 300


def _match(forecast: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any] | None:
    matching = [
        event for event in events
        if canonical_team(str(event.get("home") or "")) == canonical_team(str(forecast.get("home") or ""))
        and canonical_team(str(event.get("away") or "")) == canonical_team(str(forecast.get("away") or ""))
        and _same_tip(str(event.get("commence_time") or ""), str(forecast.get("tipoff_at") or ""))
    ]
    if len(matching) > 1:
        raise ValueError("ambiguous historical odds match")
    return matching[0] if matching else None


def _existing(path: str | Path) -> set[str]:
    return {
        str(row.get("entry_key") or "")
        for row in _read(path)
        if row.get("entry_key")
    }


def _historical_access_blocked(probe_path: str | Path) -> tuple[bool, str | None]:
    target = Path(probe_path)
    if not target.exists():
        return False, None
    try:
        probe = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False, None
    code = str(probe.get("provider_error_code") or "") or None
    return (
        probe.get("state") == "HISTORICAL_PROVIDER_ERROR"
        and code == "HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN",
        code,
    )


def recover(
    *,
    forecasts_path: str = "runtime/evidence/final_forecasts.jsonl",
    output_path: str = "runtime/research/pinnacle_historical_entry.jsonl",
    budget_path: str = "runtime/odds_budget.json",
    access_probe_path: str = "runtime/historical_pinnacle_probe.json",
    max_snapshots: int = 8,
) -> dict[str, Any]:
    if max_snapshots < 1:
        raise ValueError("max_snapshots must be positive")
    blocked, provider_code = _historical_access_blocked(access_probe_path)
    if blocked:
        return {
            "schema": "pulsar-nba-historical-pinnacle-recovery-status-v1",
            "role": ROLE,
            "status": "SKIPPED_ACCESS_BLOCKED",
            "provider_error_code": provider_code,
            "pending_forecasts": 0,
            "snapshot_groups": 0,
            "snapshots_attempted": 0,
            "added": 0,
            "failures": [],
            "odds_api_requests": 0,
            "used_for_certification": False,
            "betting_certified": False,
        }
    forecasts = [
        row for row in _read(forecasts_path)
        if row.get("role") == "PIT_FINAL_FORECAST"
    ]
    existing = _existing(output_path)
    pending = [
        row for row in forecasts
        if f"{row.get('entry_key')}|HIST_PIN" not in existing
    ]
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in pending:
        groups.setdefault(str(row["forecast_at"]), []).append(row)

    added = 0
    attempted = 0
    failures: list[str] = []
    for forecast_at in sorted(groups)[:max_snapshots]:
        try:
            reserve_odds_request(path=budget_path, purpose="historical_pinnacle_entry")
            attempted += 1
            payload = fetch_historical_nba_odds(
                date_iso=forecast_at, bookmakers="pinnacle"
            )
            snapshot_at = str(payload.get("timestamp") or "")
            if not snapshot_at:
                raise ValueError("historical Pinnacle snapshot timestamp missing")
            requested = _dt(forecast_at)
            observed = _dt(snapshot_at)
            age_minutes = (requested - observed).total_seconds() / 60.0
            if not 0.0 <= age_minutes <= 15.0:
                raise ValueError(
                    f"historical Pinnacle snapshot outside 15-minute pre-forecast window: {age_minutes:.2f}"
                )
            events = [normalize_game(raw) for raw in payload["data"]]

            for forecast in groups[forecast_at]:
                try:
                    event = _match(forecast, events)
                    if event is None:
                        raise ValueError("historical Pinnacle event not found")
                    probabilities = forecast.get("probabilities") or {}
                    specs = (
                        ("ML", "HOME", "AWAY", None, "home_ml"),
                        ("SPREAD", "HOME", "AWAY", float(probabilities["spread_line"]), "home_spread"),
                        ("TOTAL", "OVER", "UNDER", float(probabilities["total_line"]), "over"),
                    )
                    recovered: dict[str, float] = {}
                    quote_times: dict[str, str] = {}
                    for market, left, right, point, _ in specs:
                        books = event["markets"].get(market) or []
                        sharp = pinnacle_no_vig(books, left, right, point=point)
                        if sharp is None:
                            continue
                        pin = next(
                            (book for book in books
                             if str(book.get("bookmaker") or "").lower() == "pinnacle"),
                            None,
                        )
                        if pin is None or not fresh_quote(
                            pin.get("last_update"), forecast_at, max_age_minutes=15.0
                        ):
                            continue
                        recovered[market] = float(sharp[left])
                        quote_times[market] = str(pin.get("last_update"))
                    if not recovered:
                        raise ValueError("historical Pinnacle has no fresh paired forecast contract")
                    key = f"{forecast.get('entry_key')}|HIST_PIN"
                    row = {
                        "schema": SCHEMA,
                        "role": ROLE,
                        "entry_key": key,
                        "forecast_entry_key": forecast.get("entry_key"),
                        "game_id": forecast.get("game_id"),
                        "game_date": forecast.get("game_date"),
                        "home": forecast.get("home"),
                        "away": forecast.get("away"),
                        "forecast_at": forecast_at,
                        "tipoff_at": forecast.get("tipoff_at"),
                        "historical_snapshot_at": snapshot_at,
                        "snapshot_age_minutes": age_minutes,
                        "pinnacle_entry_probability": recovered,
                        "pinnacle_quote_at": quote_times,
                        "market_data_used_as_model_feature": False,
                        "used_for_certification": False,
                        "pinnacle_replacement": False,
                        "betting_certified": False,
                    }
                    append_jsonl(output_path, row)
                    existing.add(key)
                    added += 1
                except Exception as exc:
                    failures.append(
                        f"{forecast.get('entry_key')}:{type(exc).__name__}:{exc}"
                    )
        except Exception as exc:
            failures.append(
                f"snapshot:{forecast_at}:{type(exc).__name__}:{exc}"
            )

    return {
        "schema": "pulsar-nba-historical-pinnacle-recovery-status-v1",
        "role": ROLE,
        "status": "COMPLETE",
        "pending_forecasts": len(pending),
        "snapshot_groups": len(groups),
        "snapshots_attempted": attempted,
        "added": added,
        "failures": failures,
        "odds_api_requests": attempted,
        "used_for_certification": False,
        "betting_certified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forecasts", default="runtime/evidence/final_forecasts.jsonl")
    parser.add_argument("--output", default="runtime/research/pinnacle_historical_entry.jsonl")
    parser.add_argument("--budget", default="runtime/odds_budget.json")
    parser.add_argument("--access-probe", default="runtime/historical_pinnacle_probe.json")
    parser.add_argument("--max-snapshots", type=int, default=8)
    args = parser.parse_args()
    print(json.dumps(recover(
        forecasts_path=args.forecasts,
        output_path=args.output,
        budget_path=args.budget,
        access_probe_path=args.access_probe,
        max_snapshots=args.max_snapshots,
    ), indent=2))


if __name__ == "__main__":
    main()
