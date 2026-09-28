"""Evaluate immutable gamebook-provider shadow forecasts after official finals."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .communications_schedule import fetch_reference_schedule
from .gamebook_stats import fetch_gamebook
from .performance import brier, calibration_ece, logloss, mae
from .schedule import season_for_date
from .teams import canonical_team

GENERATION = "pulsar-nba-gamebook-provider-shadow-v1"


def _read(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    return [
        json.loads(line)
        for line in target.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _proper(rows: list[tuple[float, int]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0, "brier": None, "logloss": None, "ece": None}
    return {
        "n": len(rows),
        "brier": sum(brier(p, y) for p, y in rows) / len(rows),
        "logloss": sum(logloss(p, y) for p, y in rows) / len(rows),
        "ece": calibration_ece(rows),
    }


def _canonical_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("game_date") or ""),
        canonical_team(str(row.get("home") or "")),
        canonical_team(str(row.get("away") or "")),
    )


def evaluate(
    *,
    forecasts_path: str = "runtime/provider_shadow/gamebook_forecasts.jsonl",
    canonical_forecasts_path: str = "runtime/evidence/final_forecasts.jsonl",
    cache_root: str = "runtime/gamebook_reference",
    output: str = "runtime/provider_shadow/performance.json",
    reference_schedule: list[Any] | None = None,
) -> dict[str, Any]:
    forecasts = _read(forecasts_path)
    canonical_forecasts = _read(canonical_forecasts_path)
    canonical = {
        _canonical_key(row): row
        for row in canonical_forecasts
        if row.get("role") == "PIT_FINAL_FORECAST"
    }

    schedules: dict[str, list[Any]] = {}
    ml_pairs: list[tuple[float, int]] = []
    margin_pred: list[float] = []
    total_pred: list[float] = []
    actual_margin: list[float] = []
    actual_total: list[float] = []
    paired_shadow_margin: list[float] = []
    paired_v1_margin: list[float] = []
    paired_shadow_total: list[float] = []
    paired_v1_total: list[float] = []
    paired_actual_margin: list[float] = []
    paired_actual_total: list[float] = []
    paired_shadow_ml: list[tuple[float, int]] = []
    paired_v1_ml: list[tuple[float, int]] = []
    resolved: list[str] = []
    failures: list[str] = []

    for forecast in forecasts:
        if forecast.get("role") != "ALTERNATE_PROVIDER_SHADOW":
            raise ValueError("non-shadow row in gamebook provider ledger")
        if forecast.get("generation") != GENERATION:
            raise ValueError("gamebook provider generation mismatch")
        if forecast.get("production_provider_authorized") is not False:
            raise ValueError("gamebook provider row contains forbidden authority")
        if forecast.get("predictive_authority") is not False:
            raise ValueError("gamebook provider row contains forbidden predictive authority")
        if forecast.get("market_data_used") is not False:
            raise ValueError("gamebook provider row used market data")
        if forecast.get("betting_certified") is not False:
            raise ValueError("gamebook provider row contains forbidden betting certification")

        game_date = str(forecast["game_date"])
        season = season_for_date(game_date)
        if reference_schedule is not None:
            schedule = list(reference_schedule)
        else:
            if season not in schedules:
                schedules[season] = fetch_reference_schedule(season=season)
            schedule = schedules[season]
        match = next(
            (row for row in schedule if row.reference_id == forecast["game_id"]),
            None,
        )
        if match is None:
            failures.append(f"{forecast['game_id']}:schedule_identity_missing")
            continue
        try:
            final = fetch_gamebook(match, cache_root=cache_root)
        except Exception as exc:
            # Most commonly the future/postgame PDF is not published yet.
            failures.append(
                f"{forecast['game_id']}:{type(exc).__name__}:{exc}"
            )
            continue

        parsed = final["parsed"]
        margin = float(parsed["home_score"]) - float(parsed["away_score"])
        total = float(parsed["home_score"]) + float(parsed["away_score"])
        projection = forecast["score_projection"]
        p_ml = float(forecast["home_ml"])
        label = int(margin > 0)
        ml_pairs.append((p_ml, label))
        margin_pred.append(float(projection["margin_mean"]))
        total_pred.append(float(projection["total_mean"]))
        actual_margin.append(margin)
        actual_total.append(total)
        resolved.append(str(forecast["game_id"]))

        paired = canonical.get(_canonical_key(forecast))
        if paired is not None:
            paired_shadow_margin.append(float(projection["margin_mean"]))
            paired_shadow_total.append(float(projection["total_mean"]))
            paired_v1_margin.append(float(paired["baseline_margin"]))
            paired_v1_total.append(float(paired["baseline_total"]))
            paired_actual_margin.append(margin)
            paired_actual_total.append(total)
            probs = paired.get("probabilities") or {}
            if probs.get("home_ml") is not None:
                paired_shadow_ml.append((p_ml, label))
                paired_v1_ml.append((float(probs["home_ml"]), label))

    proper = _proper(ml_pairs)
    paired_shadow_proper = _proper(paired_shadow_ml)
    paired_v1_proper = _proper(paired_v1_ml)
    completeness_values = [
        float(row.get("gamebook_completeness"))
        for row in forecasts
        if row.get("gamebook_completeness") is not None
    ]
    report = {
        "schema": "pulsar-nba-gamebook-provider-shadow-performance-v1",
        "role": "MANUAL_REVIEW_ONLY",
        "generation": GENERATION,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "resolved_n": len(resolved),
        "resolved_game_ids": resolved,
        "ml_brier": proper["brier"],
        "ml_logloss": proper["logloss"],
        "ml_ece": proper["ece"],
        "margin_mae": mae(margin_pred, actual_margin) if resolved else None,
        "total_mae": mae(total_pred, actual_total) if resolved else None,
        "paired_v1_n": len(paired_actual_margin),
        "minimum_gamebook_completeness": (
            min(completeness_values) if completeness_values else None
        ),
        "paired_shadow_margin_mae": (
            mae(paired_shadow_margin, paired_actual_margin)
            if paired_actual_margin else None
        ),
        "paired_v1_margin_mae": (
            mae(paired_v1_margin, paired_actual_margin)
            if paired_actual_margin else None
        ),
        "paired_shadow_total_mae": (
            mae(paired_shadow_total, paired_actual_total)
            if paired_actual_total else None
        ),
        "paired_v1_total_mae": (
            mae(paired_v1_total, paired_actual_total)
            if paired_actual_total else None
        ),
        "paired_shadow_ml_brier": paired_shadow_proper["brier"],
        "paired_v1_ml_brier": paired_v1_proper["brier"],
        "production_provider_authorized": False,
        "predictive_authority": False,
        "betting_certified": False,
        "review_ready": False,
        "failures": failures,
        "next_action": (
            "collect prospective shadow evidence; provider promotion requires "
            "separate human review, frozen generation and fresh validation"
        ),
    }
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate gamebook-provider prospective shadow evidence"
    )
    parser.add_argument(
        "--forecasts",
        default="runtime/provider_shadow/gamebook_forecasts.jsonl",
    )
    parser.add_argument(
        "--canonical-forecasts",
        default="runtime/evidence/final_forecasts.jsonl",
    )
    parser.add_argument(
        "--cache-root",
        default="runtime/gamebook_reference",
    )
    parser.add_argument(
        "--output",
        default="runtime/provider_shadow/performance.json",
    )
    args = parser.parse_args()
    result = evaluate(
        forecasts_path=args.forecasts,
        canonical_forecasts_path=args.canonical_forecasts,
        cache_root=args.cache_root,
        output=args.output,
    )
    print(json.dumps({
        "resolved_n": result["resolved_n"],
        "paired_v1_n": result["paired_v1_n"],
        "production_provider_authorized": False,
    }, indent=2))


if __name__ == "__main__":
    main()
