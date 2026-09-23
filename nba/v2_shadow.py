"""Chronological, point-in-time-only shadow calibrator.

Requires archived pre-tip projections and independently observed final scores.
Does not ingest odds, modify the live champion, or authorize wagers.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from . import MODEL_GENERATION
from .distribution import normal_cdf
from .performance import brier, logloss, calibration_ece, mae

SHADOW_GENERATION = "pulsar-nba-v2-shadow-calibration-v1"


def _dt(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("PIT timestamps must include timezone")
    return result.astimezone(timezone.utc)


def _number(row: dict[str, Any], name: str) -> float:
    result = float(row[name])
    if not math.isfinite(result):
        raise ValueError(f"non-finite {name}")
    return result


def validate_row(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("model_generation") != MODEL_GENERATION:
        raise ValueError("mixed champion generations are forbidden in shadow evaluation")
    if any("odds" in key.lower() or "market" in key.lower()
           for key in row if key != "model_generation"):
        raise ValueError("market data must not enter training inputs")
    if not row.get("game_id") or not re.fullmatch(r"[a-fA-F0-9]{64}", str(row.get("source_snapshot_sha256") or "")):
        raise ValueError("game ID and 64-character source snapshot hash are required")
    snapshot, forecast, tip, outcome = (
        _dt(str(row[key])) for key in ("source_snapshot_at", "forecast_at", "tipoff_at", "outcome_at")
    )
    if not snapshot <= forecast < tip < outcome:
        raise ValueError("look-ahead: source/forecast/tip/outcome timestamps are not ordered")
    clean = dict(row)
    for name in ("baseline_margin", "baseline_total", "baseline_margin_sd",
                 "baseline_total_sd", "home_score", "away_score"):
        clean[name] = _number(row, name)
    if clean["baseline_margin_sd"] <= 0 or clean["baseline_total_sd"] <= 0:
        raise ValueError("positive baseline standard deviations are required")
    if clean["home_score"] < 0 or clean["away_score"] < 0:
        raise ValueError("final scores must be nonnegative")
    return clean


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows = [validate_row(json.loads(line)) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]
    if len({r["game_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate game IDs in PIT training corpus")
    return sorted(rows, key=lambda r: (_dt(r["tipoff_at"]), str(r["game_id"])))


def _fit_affine(x: list[float], y: list[float], *, ridge: float, intercept_limit: float) -> tuple[float, float]:
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    variance = sum((value - mean_x) ** 2 for value in x)
    covariance = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    # Ridge prior around slope 1 (original frozen champion) rather than slope 0.
    slope = max(.5, min(1.5, (covariance + ridge) / (variance + ridge)))
    intercept = max(-intercept_limit, min(intercept_limit, mean_y - slope * mean_x))
    return intercept, slope


def _residual_sd(x: list[float], y: list[float], intercept: float, slope: float,
                 *, floor: float, ceiling: float) -> float:
    ss = sum((actual - intercept - slope * projected) ** 2 for projected, actual in zip(x, y))
    return max(floor, min(ceiling, math.sqrt(ss / max(1, len(x) - 2))))


@dataclass(frozen=True)
class ShadowModel:
    margin_intercept: float
    margin_slope: float
    total_intercept: float
    total_slope: float
    margin_sd: float
    total_sd: float
    train_n: int
    train_cutoff: str
    training_fingerprint: str
    generation: str = SHADOW_GENERATION

    def predict(self, row: dict[str, Any]) -> dict[str, float]:
        margin = self.margin_intercept + self.margin_slope * float(row["baseline_margin"])
        total = self.total_intercept + self.total_slope * float(row["baseline_total"])
        return {
            "margin_mean": margin, "total_mean": total,
            "home_ml": normal_cdf(margin / self.margin_sd),
        }


def fit_shadow(train: list[dict[str, Any]], *, train_cutoff: str,
               minimum_train: int = 400) -> ShadowModel:
    if len(train) < minimum_train:
        raise ValueError(f"insufficient chronological training sample: {len(train)} < {minimum_train}")
    cutoff = _dt(train_cutoff)
    if any(_dt(row["outcome_at"]) > cutoff for row in train):
        raise ValueError("training outcomes were unavailable at training cutoff")
    xs_m = [_number(r, "baseline_margin") for r in train]
    ys_m = [_number(r, "home_score") - _number(r, "away_score") for r in train]
    xs_t = [_number(r, "baseline_total") for r in train]
    ys_t = [_number(r, "home_score") + _number(r, "away_score") for r in train]
    im, sm = _fit_affine(xs_m, ys_m, ridge=400.0, intercept_limit=8.0)
    it, st = _fit_affine(xs_t, ys_t, ridge=1600.0, intercept_limit=15.0)
    inputs = [(r["game_id"], r["source_snapshot_sha256"], r["outcome_at"],
               r["home_score"], r["away_score"]) for r in train]
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ShadowModel(im, sm, it, st,
                       _residual_sd(xs_m, ys_m, im, sm, floor=8, ceiling=25),
                       _residual_sd(xs_t, ys_t, it, st, floor=12, ceiling=35),
                       len(train), train_cutoff, digest)


def _score(rows: list[dict[str, Any]], *, model: ShadowModel | None) -> dict[str, float | int]:
    estimates = []
    for row in rows:
        if model is None:
            estimate = {
                "margin_mean": float(row["baseline_margin"]),
                "total_mean": float(row["baseline_total"]),
                "home_ml": normal_cdf(float(row["baseline_margin"]) / float(row["baseline_margin_sd"])),
            }
        else:
            estimate = model.predict(row)
        estimates.append((estimate, row))
    probs = [(p["home_ml"], int(r["home_score"] > r["away_score"])) for p, r in estimates]
    return {
        "n": len(rows),
        "ml_brier": sum(brier(p, y) for p, y in probs) / len(probs),
        "ml_logloss": sum(logloss(p, y) for p, y in probs) / len(probs),
        "ml_ece": calibration_ece(probs),
        "margin_mae": mae((p["margin_mean"] for p, _ in estimates),
                          (r["home_score"] - r["away_score"] for _, r in estimates)),
        "total_mae": mae((p["total_mean"] for p, _ in estimates),
                         (r["home_score"] + r["away_score"] for _, r in estimates)),
    }


def evaluate(
    rows: list[dict[str, Any]], *, train_cutoff: str, holdout_start: str,
    minimum_train: int = 400, minimum_holdout: int = 100,
) -> dict[str, Any]:
    if _dt(holdout_start) <= _dt(train_cutoff):
        raise ValueError("holdout must start strictly after training cutoff")
    validated = [validate_row(row) for row in rows]
    if len({r["game_id"] for r in validated}) != len(validated):
        raise ValueError("duplicate game IDs")
    train = [r for r in validated if _dt(r["outcome_at"]) <= _dt(train_cutoff)]
    holdout = [r for r in validated if _dt(r["forecast_at"]) >= _dt(holdout_start)]
    if len(holdout) < minimum_holdout:
        raise ValueError("insufficient out-of-sample holdout observations")
    if {r["game_id"] for r in train} & {r["game_id"] for r in holdout}:
        raise ValueError("train/holdout overlap")
    model = fit_shadow(train, train_cutoff=train_cutoff, minimum_train=minimum_train)
    return {
        "role": "SHADOW", "promoted": False, "auto_betting_certification": False,
        "champion_generation": MODEL_GENERATION, "shadow_generation": SHADOW_GENERATION,
        "train_cutoff": train_cutoff, "holdout_start": holdout_start,
        "model": asdict(model),
        "holdout_champion": _score(holdout, model=None),
        "holdout_shadow": _score(holdout, model=model),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="PIT-only NBA V2 shadow walk-forward")
    parser.add_argument("--input", required=True, help="archived PIT predictions with independently observed results")
    parser.add_argument("--train-cutoff", required=True, help="ISO timestamp; train labels known by this time")
    parser.add_argument("--holdout-start", required=True, help="ISO timestamp; strictly after train cutoff")
    parser.add_argument("--output", default="runtime/research/v2_shadow.json")
    args = parser.parse_args()
    result = evaluate(load_jsonl(args.input), train_cutoff=args.train_cutoff,
                      holdout_start=args.holdout_start)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"role": "SHADOW", "train_n": result["model"]["train_n"],
                      "holdout_n": result["holdout_shadow"]["n"],
                      "output": str(target)}))


if __name__ == "__main__":
    main()
