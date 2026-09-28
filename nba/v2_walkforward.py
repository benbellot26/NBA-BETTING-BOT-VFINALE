"""Expanding-window, point-in-time evaluation of the learned V2 challenger."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .distribution import normal_cdf
from .performance import brier, calibration_ece, logloss, mae
from .v2_dataset import load_training_jsonl, validate_training_row
from .v2_model import LEARNED_GENERATION, fit_learned_v2


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("walk-forward timestamps require timezone")
    return parsed.astimezone(timezone.utc)


def _market_probabilities(estimate: dict[str, float], row: dict[str, Any]) -> dict[str, float | None]:
    evaluation = row.get("evaluation_only") or {}
    spread_line = evaluation.get("spread_line")
    total_line = evaluation.get("total_line")
    home_spread = None
    over = None
    if spread_line is not None:
        home_spread = normal_cdf(
            (float(estimate["margin_mean"]) + float(spread_line)) / float(estimate["margin_sd"])
        )
    if total_line is not None:
        over = normal_cdf(
            (float(estimate["total_mean"]) - float(total_line)) / float(estimate["total_sd"])
        )
    return {"home_spread": home_spread, "over": over}


def _baseline(row: dict[str, Any]) -> dict[str, float]:
    margin = float(row["baseline_margin"])
    total = float(row["baseline_total"])
    margin_sd = float(row["baseline_margin_sd"])
    total_sd = float(row["baseline_total_sd"])
    return {
        "margin_mean": margin,
        "total_mean": total,
        "margin_sd": margin_sd,
        "total_sd": total_sd,
        "home_ml": normal_cdf(margin / margin_sd),
    }


def _score(pairs: list[tuple[dict[str, float], dict[str, Any]]]) -> dict[str, Any]:
    if not pairs:
        raise ValueError("cannot score empty V2 holdout")
    ml_pairs: list[tuple[float, int]] = []
    spread_pairs: list[tuple[float, int]] = []
    total_pairs: list[tuple[float, int]] = []
    margin_pred, margin_real, total_pred, total_real = [], [], [], []
    for estimate, row in pairs:
        home, away = float(row["home_score"]), float(row["away_score"])
        margin_actual = home - away
        total_actual = home + away
        ml_pairs.append((float(estimate["home_ml"]), int(margin_actual > 0)))
        margin_pred.append(float(estimate["margin_mean"]))
        margin_real.append(margin_actual)
        total_pred.append(float(estimate["total_mean"]))
        total_real.append(total_actual)
        market = _market_probabilities(estimate, row)
        evaluation = row.get("evaluation_only") or {}
        if market["home_spread"] is not None:
            delta = margin_actual + float(evaluation["spread_line"])
            if delta != 0:
                spread_pairs.append((float(market["home_spread"]), int(delta > 0)))
        if market["over"] is not None:
            delta = total_actual - float(evaluation["total_line"])
            if delta != 0:
                total_pairs.append((float(market["over"]), int(delta > 0)))

    def proper(rows: list[tuple[float, int]]) -> dict[str, Any]:
        if not rows:
            return {"n": 0, "brier": None, "logloss": None, "ece": None}
        return {
            "n": len(rows),
            "brier": sum(brier(p, y) for p, y in rows) / len(rows),
            "logloss": sum(logloss(p, y) for p, y in rows) / len(rows),
            "ece": calibration_ece(rows),
        }

    ml = proper(ml_pairs)
    spread = proper(spread_pairs)
    total = proper(total_pairs)
    return {
        "n": len(pairs),
        "ml_brier": ml["brier"], "ml_logloss": ml["logloss"], "ml_ece": ml["ece"],
        "margin_mae": mae(margin_pred, margin_real),
        "total_mae": mae(total_pred, total_real),
        "spread_n": spread["n"], "spread_brier": spread["brier"],
        "spread_logloss": spread["logloss"], "spread_ece": spread["ece"],
        "total_n": total["n"], "total_brier": total["brier"],
        "total_logloss": total["logloss"], "total_ece": total["ece"],
    }


def _score_pinnacle(rows: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[tuple[float, int]]] = {"ML": [], "SPREAD": [], "TOTAL": []}
    for row in rows:
        evaluation = row.get("evaluation_only") or {}
        sharp = evaluation.get("pinnacle_entry_probability") or {}
        home, away = float(row["home_score"]), float(row["away_score"])
        margin_actual = home - away
        total_actual = home + away
        if sharp.get("ML") is not None and margin_actual != 0:
            buckets["ML"].append((float(sharp["ML"]), int(margin_actual > 0)))
        if sharp.get("SPREAD") is not None and evaluation.get("spread_line") is not None:
            delta = margin_actual + float(evaluation["spread_line"])
            if delta != 0:
                buckets["SPREAD"].append((float(sharp["SPREAD"]), int(delta > 0)))
        if sharp.get("TOTAL") is not None and evaluation.get("total_line") is not None:
            delta = total_actual - float(evaluation["total_line"])
            if delta != 0:
                buckets["TOTAL"].append((float(sharp["TOTAL"]), int(delta > 0)))
    out: dict[str, Any] = {}
    for market, values in buckets.items():
        key = market.lower()
        out[f"{key}_n"] = len(values)
        out[f"{key}_brier"] = (
            sum(brier(p, y) for p, y in values) / len(values) if values else None
        )
        out[f"{key}_logloss"] = (
            sum(logloss(p, y) for p, y in values) / len(values) if values else None
        )
        out[f"{key}_ece"] = calibration_ece(values) if values else None
    return out


def walk_forward(
    rows: list[dict[str, Any]],
    *,
    minimum_train: int = 400,
    minimum_holdout: int = 100,
    step: int = 50,
    alpha_mean: float = 25.0,
    alpha_variance: float = 50.0,
) -> dict[str, Any]:
    if step < 1:
        raise ValueError("walk-forward step must be >= 1")
    ordered = sorted(
        (validate_training_row(row) for row in rows),
        key=lambda row: (_dt(row["forecast_at"]), str(row["game_id"])),
    )
    if len(ordered) < minimum_train + minimum_holdout:
        raise ValueError(
            f"insufficient corpus for walk-forward: {len(ordered)} < "
            f"{minimum_train + minimum_holdout}"
        )
    challenger_pairs: list[tuple[dict[str, float], dict[str, Any]]] = []
    champion_pairs: list[tuple[dict[str, float], dict[str, Any]]] = []
    holdout_rows: list[dict[str, Any]] = []
    folds: list[dict[str, Any]] = []

    cursor = minimum_train
    while cursor < len(ordered):
        block = ordered[cursor:cursor + step]
        if not block:
            break
        first_forecast = min(_dt(row["forecast_at"]) for row in block)
        candidates = ordered[:cursor]
        train = [row for row in candidates if _dt(row["outcome_at"]) <= first_forecast]
        if len(train) < minimum_train:
            cursor += len(block)
            continue
        model = fit_learned_v2(
            train,
            minimum_train=minimum_train,
            alpha_mean=alpha_mean,
            alpha_variance=alpha_variance,
            train_cutoff=first_forecast.isoformat(),
        )
        for row in block:
            challenger_pairs.append((model.predict(row), row))
            champion_pairs.append((_baseline(row), row))
            holdout_rows.append(row)
        folds.append({
            "train_n": len(train),
            "test_n": len(block),
            "train_cutoff": first_forecast.isoformat(),
            "first_test_game": block[0]["game_id"],
            "last_test_game": block[-1]["game_id"],
            "training_fingerprint": model.training_fingerprint,
            "variance_training": model.variance_training,
        })
        cursor += len(block)

    if len(holdout_rows) < minimum_holdout:
        raise ValueError(
            f"insufficient PIT holdout after outcome-availability filtering: "
            f"{len(holdout_rows)} < {minimum_holdout}"
        )
    champion = _score(champion_pairs)
    challenger = _score(challenger_pairs)
    pinnacle = _score_pinnacle(holdout_rows)
    return {
        "schema": "pulsar-nba-v2-walk-forward-v1",
        "role": "SHADOW",
        "promoted": False,
        "auto_betting_certification": False,
        "shadow_generation": LEARNED_GENERATION,
        "training_inputs": "v2_features_only",
        "market_data_used_as_feature": False,
        "holdout_champion": champion,
        "holdout_shadow": challenger,
        "holdout_pinnacle_entry": pinnacle,
        "folds": folds,
        "holdout_game_ids": [str(row["game_id"]) for row in holdout_rows],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="PIT learned V2 walk-forward evaluation")
    parser.add_argument("--input", default="runtime/research/pit_dataset.jsonl")
    parser.add_argument("--output", default="runtime/research/v2_learned_shadow.json")
    parser.add_argument("--minimum-train", type=int, default=400)
    parser.add_argument("--minimum-holdout", type=int, default=100)
    parser.add_argument("--step", type=int, default=50)
    args = parser.parse_args()
    rows = load_training_jsonl(args.input)
    report = walk_forward(
        rows,
        minimum_train=args.minimum_train,
        minimum_holdout=args.minimum_holdout,
        step=args.step,
    )
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "role": report["role"],
        "holdout_n": report["holdout_shadow"]["n"],
        "folds": len(report["folds"]),
        "output": str(target),
    }, indent=2))


if __name__ == "__main__":
    main()
