"""Prospective learned-V2 shadow inference.

This runtime can only append SHADOW forecasts. It cannot emit BET decisions,
stakes, certification, or modify the frozen V1 champion.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from . import MODEL_GENERATION
from .distribution import normal_cdf
from .replay_export import export as export_replay
from .tracking import append_jsonl
from .v2_dataset import load_training_jsonl
from .v2_model import LEARNED_GENERATION, fit_learned_v2

SCHEMA = "pulsar-nba-v2-prospective-forecast-v1"


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("V2 prospective timestamps require timezone")
    return parsed.astimezone(timezone.utc)


def _read_json(path: str | Path) -> dict[str, Any] | None:
    target = Path(path)
    if not target.exists():
        return None
    value = json.loads(target.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    return [
        json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sharp_probability(game: dict[str, Any], selection: str) -> float | None:
    for candidate in (game.get("decision") or {}).get("candidates") or []:
        if candidate.get("selection") == selection and candidate.get("sharp_probability") is not None:
            return float(candidate["sharp_probability"])
    return None


def _refresh_training_rows(
    *,
    forecasts_path: str,
    outcomes_path: str,
    dataset_path: str,
) -> list[dict[str, Any]]:
    if not Path(forecasts_path).exists() or not Path(outcomes_path).exists():
        return []
    try:
        export_replay(
            forecasts_path=forecasts_path,
            outcomes_path=outcomes_path,
            output=dataset_path,
        )
        return load_training_jsonl(dataset_path)
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
        # Lack of enriched prospective history is an expected startup state.
        if "no forecasts contain" in str(exc) or "empty" in str(exc).lower():
            return []
        raise


def _status(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run(
    *,
    live_run_path: str = "runtime/live_run.json",
    forecasts_path: str = "runtime/evidence/final_forecasts.jsonl",
    outcomes_path: str = "runtime/evidence/final_outcomes.jsonl",
    dataset_path: str = "runtime/research/pit_dataset.jsonl",
    output_path: str = "runtime/research/v2_live_forecasts.jsonl",
    status_path: str = "runtime/research/v2_live_status.json",
    minimum_train: int = 400,
    training_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    live = _read_json(live_run_path)
    result: dict[str, Any] = {
        "schema": "pulsar-nba-v2-live-status-v1",
        "role": "SHADOW",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "STARTED",
        "minimum_train": minimum_train,
        "training_n": 0,
        "added": 0,
        "auto_promote": False,
        "betting_certified": False,
    }
    if not live:
        result["status"] = "NO_LIVE_RUN"
        _status(status_path, result)
        return result
    if live.get("operating_mode") != "regular":
        result["status"] = "NON_REGULAR_RUN"
        _status(status_path, result)
        return result

    games = [
        game for game in live.get("games") or []
        if game.get("phase") == "FINAL"
        and game.get("v2_features") is not None
        and game.get("source_snapshot_sha256")
        and game.get("commence_time")
    ]
    if not games:
        result["status"] = "NO_FINAL_GAMES"
        _status(status_path, result)
        return result

    earliest_forecast = min(_dt(str(game["analyzed_at"])) for game in games)
    rows = list(training_rows) if training_rows is not None else _refresh_training_rows(
        forecasts_path=forecasts_path,
        outcomes_path=outcomes_path,
        dataset_path=dataset_path,
    )
    train = [
        row for row in rows
        if _dt(str(row["outcome_at"])) <= earliest_forecast
    ]
    result["training_n"] = len(train)
    if len(train) < minimum_train:
        result["status"] = "INSUFFICIENT_TRAINING"
        _status(status_path, result)
        return result

    model = fit_learned_v2(
        train,
        minimum_train=minimum_train,
        train_cutoff=earliest_forecast.isoformat(),
    )
    existing = {
        str(row.get("entry_key")) for row in _read_jsonl(output_path)
        if row.get("entry_key")
    }
    added = 0
    for game in sorted(games, key=lambda row: str(row["game_id"])):
        forecast_at = _dt(str(game["analyzed_at"]))
        tipoff_at = _dt(str(game["commence_time"]))
        if forecast_at >= tipoff_at:
            raise ValueError("V2 shadow forecast is not pre-tip")
        entry_key = f"{game['game_id']}|{LEARNED_GENERATION}|FINAL"
        if entry_key in existing:
            continue
        inference = {
            "v2_features": game["v2_features"],
            "source_snapshot_sha256": game["source_snapshot_sha256"],
        }
        prediction = model.predict(inference)
        probabilities = game.get("probabilities") or {}
        spread_line = float(probabilities["spread_line"])
        total_line = float(probabilities["total_line"])
        prediction.update({
            "home_spread": normal_cdf(
                (prediction["margin_mean"] + spread_line) / prediction["margin_sd"]
            ),
            "over": normal_cdf(
                (prediction["total_mean"] - total_line) / prediction["total_sd"]
            ),
            "spread_line": spread_line,
            "total_line": total_line,
        })
        score = game.get("score_projection") or {}
        champion = {
            "margin_mean": float(score["margin_mean"]),
            "total_mean": float(score["total_mean"]),
            "margin_sd": float(score["margin_sd"]),
            "total_sd": float(score["total_sd"]),
            "home_ml": float(probabilities["home_ml"]),
            "home_spread": float(probabilities["home_spread"]),
            "over": float(probabilities["over"]),
            "spread_line": spread_line,
            "total_line": total_line,
        }
        sharp = {
            "ML": _sharp_probability(game, "home_ml"),
            "SPREAD": _sharp_probability(game, "home_spread"),
            "TOTAL": _sharp_probability(game, "over"),
        }
        record = {
            "schema": SCHEMA,
            "role": "SHADOW_PIT_FORECAST",
            "entry_key": entry_key,
            "game_id": str(game["game_id"]),
            "home": game.get("home"),
            "away": game.get("away"),
            "forecast_at": forecast_at.isoformat(),
            "tipoff_at": tipoff_at.isoformat(),
            "source_snapshot_sha256": game["source_snapshot_sha256"],
            "v2_feature_sha256": game["v2_features"]["sha256"],
            "champion_generation": MODEL_GENERATION,
            "shadow_generation": LEARNED_GENERATION,
            "training_n": model.train_n,
            "training_fingerprint": model.training_fingerprint,
            "trained_through": model.trained_through,
            "variance_training": model.variance_training,
            "market_data_used_as_feature": False,
            "prediction": prediction,
            "champion": champion,
            "evaluation_only": {
                "spread_line": spread_line,
                "total_line": total_line,
                "pinnacle_entry_probability": {
                    key: value for key, value in sharp.items() if value is not None
                },
            },
            "promoted": False,
            "betting_certified": False,
        }
        append_jsonl(output_path, record)
        existing.add(entry_key)
        added += 1

    result.update({
        "status": "SHADOW_FORECASTS_RECORDED" if added else "NO_NEW_SHADOW_FORECASTS",
        "added": added,
        "training_n": model.train_n,
        "training_fingerprint": model.training_fingerprint,
        "trained_through": model.trained_through,
    })
    _status(status_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Record prospective learned V2 shadow forecasts")
    parser.add_argument("--live-run", default="runtime/live_run.json")
    parser.add_argument("--forecasts", default="runtime/evidence/final_forecasts.jsonl")
    parser.add_argument("--outcomes", default="runtime/evidence/final_outcomes.jsonl")
    parser.add_argument("--dataset", default="runtime/research/pit_dataset.jsonl")
    parser.add_argument("--output", default="runtime/research/v2_live_forecasts.jsonl")
    parser.add_argument("--status", default="runtime/research/v2_live_status.json")
    parser.add_argument("--minimum-train", type=int, default=400)
    args = parser.parse_args()
    result = run(
        live_run_path=args.live_run,
        forecasts_path=args.forecasts,
        outcomes_path=args.outcomes,
        dataset_path=args.dataset,
        output_path=args.output,
        status_path=args.status,
        minimum_train=args.minimum_train,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
