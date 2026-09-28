"""Deterministic learned challenger for NBA margin, total and conditional variance.

This module intentionally uses only the Python standard library. It is a shadow
research model: it cannot promote itself and it never receives market inputs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
from typing import Any, Callable

from .distribution import normal_cdf
from .v2_dataset import (
    dataset_fingerprint,
    feature_vector,
    inference_feature_vector,
    targets,
    validate_training_row,
)
from .v2_features import FEATURE_NAMES, FEATURE_SCHEMA

LEARNED_GENERATION = "pulsar-nba-v2-ridge-heteroskedastic-v1"


def _dt(value: str) -> datetime:
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("V2 timestamps require timezone")
    return result.astimezone(timezone.utc)


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting for the small ridge system."""
    n = len(rhs)
    a = [list(row) + [float(rhs[i])] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise ValueError("singular V2 ridge system")
        if pivot != col:
            a[col], a[pivot] = a[pivot], a[col]
        scale = a[col][col]
        for j in range(col, n + 1):
            a[col][j] /= scale
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            if abs(factor) < 1e-18:
                continue
            for j in range(col, n + 1):
                a[row][j] -= factor * a[col][j]
    return [a[i][n] for i in range(n)]


@dataclass(frozen=True)
class RidgeRegressor:
    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    alpha: float
    train_n: int

    def predict_vector(self, values: list[float]) -> float:
        if len(values) != len(self.feature_names):
            raise ValueError("V2 feature vector width mismatch")
        return self.intercept + sum(
            coefficient * ((float(value) - mean) / scale)
            for value, mean, scale, coefficient
            in zip(values, self.means, self.scales, self.coefficients)
        )

    def predict_row(self, row: dict[str, Any]) -> float:
        return self.predict_vector(inference_feature_vector(row))


def _fit_ridge(
    rows: list[dict[str, Any]],
    target: Callable[[dict[str, Any]], float],
    *,
    alpha: float,
) -> RidgeRegressor:
    if not rows:
        raise ValueError("cannot fit V2 ridge on empty rows")
    x = [feature_vector(row) for row in rows]
    y = [float(target(row)) for row in rows]
    p = len(FEATURE_NAMES)
    means = [sum(row[j] for row in x) / len(x) for j in range(p)]
    scales = []
    for j in range(p):
        variance = sum((row[j] - means[j]) ** 2 for row in x) / max(1, len(x) - 1)
        scale = math.sqrt(max(0.0, variance))
        scales.append(scale if scale > 1e-9 else 1.0)
    z = [[(row[j] - means[j]) / scales[j] for j in range(p)] for row in x]
    y_mean = sum(y) / len(y)
    centered_y = [value - y_mean for value in y]
    gram = [[0.0 for _ in range(p)] for _ in range(p)]
    rhs = [0.0 for _ in range(p)]
    for row, label in zip(z, centered_y):
        for j in range(p):
            rhs[j] += row[j] * label
            for k in range(j, p):
                gram[j][k] += row[j] * row[k]
    for j in range(p):
        for k in range(j):
            gram[j][k] = gram[k][j]
        gram[j][j] += float(alpha)
    coefficients = _solve(gram, rhs)
    return RidgeRegressor(
        feature_names=tuple(FEATURE_NAMES),
        means=tuple(means),
        scales=tuple(scales),
        coefficients=tuple(coefficients),
        intercept=y_mean,
        alpha=float(alpha),
        train_n=len(rows),
    )


@dataclass(frozen=True)
class LearnedV2Model:
    margin_model: RidgeRegressor
    total_model: RidgeRegressor
    margin_log_mae_model: RidgeRegressor
    total_log_mae_model: RidgeRegressor
    train_n: int
    trained_through: str
    training_fingerprint: str
    variance_training: str
    feature_schema: str = FEATURE_SCHEMA
    generation: str = LEARNED_GENERATION
    role: str = "SHADOW"

    def predict(self, row: dict[str, Any]) -> dict[str, float]:
        values = inference_feature_vector(row)
        margin = self.margin_model.predict_vector(values)
        total = self.total_model.predict_vector(values)
        margin_log_mae = max(
            -2.0, min(4.0, self.margin_log_mae_model.predict_vector(values))
        )
        total_log_mae = max(
            -2.0, min(4.0, self.total_log_mae_model.predict_vector(values))
        )
        margin_mae = max(0.25, math.exp(margin_log_mae) - 0.5)
        total_mae = max(0.25, math.exp(total_log_mae) - 0.5)
        # For a zero-mean Gaussian residual E|X| = sigma * sqrt(2/pi).
        margin_sd = max(7.5, min(24.0, margin_mae * math.sqrt(math.pi / 2.0)))
        total_sd = max(10.0, min(32.0, total_mae * math.sqrt(math.pi / 2.0)))
        return {
            "margin_mean": margin,
            "total_mean": total,
            "margin_sd": margin_sd,
            "total_sd": total_sd,
            "home_ml": normal_cdf(margin / margin_sd),
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _actual_margin(row: dict[str, Any]) -> float:
    return targets(row)[0]


def _actual_total(row: dict[str, Any]) -> float:
    return targets(row)[1]


def _variance_rows(
    rows: list[dict[str, Any]],
    *,
    alpha_mean: float,
    minimum_head: int,
) -> tuple[list[dict[str, Any]], list[float], list[float], str]:
    """Generate residual labels from a chronological holdout inside training.

    The variance model therefore learns errors made on data the temporary mean
    model did not train on. Small synthetic/unit-test samples fall back to
    in-sample residuals, but production defaults are large enough for holdout.
    """
    split = max(minimum_head, int(len(rows) * 0.70))
    if split <= len(rows) - max(20, len(FEATURE_NAMES) // 2):
        head, tail = rows[:split], rows[split:]
        margin = _fit_ridge(head, _actual_margin, alpha=alpha_mean)
        total = _fit_ridge(head, _actual_total, alpha=alpha_mean)
        source = "chronological_internal_holdout"
        selected = tail
    else:
        margin = _fit_ridge(rows, _actual_margin, alpha=alpha_mean)
        total = _fit_ridge(rows, _actual_total, alpha=alpha_mean)
        source = "in_sample_fallback"
        selected = rows
    margin_labels = [
        math.log(abs(_actual_margin(row) - margin.predict_row(row)) + 0.5)
        for row in selected
    ]
    total_labels = [
        math.log(abs(_actual_total(row) - total.predict_row(row)) + 0.5)
        for row in selected
    ]
    return selected, margin_labels, total_labels, source


def fit_learned_v2(
    rows: list[dict[str, Any]],
    *,
    minimum_train: int = 400,
    alpha_mean: float = 25.0,
    alpha_variance: float = 50.0,
    train_cutoff: str | None = None,
) -> LearnedV2Model:
    validated = sorted(
        (validate_training_row(row) for row in rows),
        key=lambda row: (_dt(row["forecast_at"]), str(row["game_id"])),
    )
    if len(validated) < minimum_train:
        raise ValueError(
            f"insufficient learned V2 training sample: {len(validated)} < {minimum_train}"
        )
    if train_cutoff is not None:
        cutoff = _dt(train_cutoff)
        if any(_dt(row["outcome_at"]) > cutoff for row in validated):
            raise ValueError("V2 training label was unavailable at train cutoff")
    margin_model = _fit_ridge(validated, _actual_margin, alpha=alpha_mean)
    total_model = _fit_ridge(validated, _actual_total, alpha=alpha_mean)
    variance_rows, margin_log_errors, total_log_errors, variance_training = _variance_rows(
        validated, alpha_mean=alpha_mean, minimum_head=max(40, minimum_train // 2)
    )
    margin_targets = {
        str(row["game_id"]): value for row, value in zip(variance_rows, margin_log_errors)
    }
    total_targets = {
        str(row["game_id"]): value for row, value in zip(variance_rows, total_log_errors)
    }
    margin_var_model = _fit_ridge(
        variance_rows,
        lambda row: margin_targets[str(row["game_id"])],
        alpha=alpha_variance,
    )
    total_var_model = _fit_ridge(
        variance_rows,
        lambda row: total_targets[str(row["game_id"])],
        alpha=alpha_variance,
    )
    trained_through = max(str(row["outcome_at"]) for row in validated)
    return LearnedV2Model(
        margin_model=margin_model,
        total_model=total_model,
        margin_log_mae_model=margin_var_model,
        total_log_mae_model=total_var_model,
        train_n=len(validated),
        trained_through=trained_through,
        training_fingerprint=dataset_fingerprint(validated),
        variance_training=variance_training,
    )
