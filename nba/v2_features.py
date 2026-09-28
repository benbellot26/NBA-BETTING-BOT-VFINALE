"""Point-in-time feature contract for the learned V2 shadow.

Only basketball/context inputs are allowed here. Market/odds/price information is
explicitly forbidden from the training feature payload.
"""
from __future__ import annotations

from dataclasses import asdict
import math
from typing import Any, Iterable

from .model import GameContext, ScoreProjection, TeamMetrics
from .rotations import RotationPlayer

FEATURE_SCHEMA = "pulsar-nba-v2-features-v1"
FORBIDDEN_FEATURE_TOKENS = (
    "odds", "market", "price", "book", "pinnacle", "sharp",
    "breakeven", "spread_line", "total_line",
)

FEATURE_NAMES = (
    "baseline_margin", "baseline_total", "baseline_possessions",
    "baseline_margin_sd", "baseline_total_sd",
    "home_ortg", "away_ortg", "home_drtg", "away_drtg",
    "home_pace", "away_pace",
    "home_efg", "away_efg", "home_tov_pct", "away_tov_pct",
    "home_orb_pct", "away_orb_pct", "home_ft_rate", "away_ft_rate",
    "home_three_pa_rate", "away_three_pa_rate",
    "home_rim_rate", "away_rim_rate",
    "home_transition_rate", "away_transition_rate",
    "home_rest_days", "away_rest_days", "home_b2b", "away_b2b",
    "home_three_in_four", "away_three_in_four",
    "home_travel_km", "away_travel_km",
    "home_timezone_shift", "away_timezone_shift", "altitude_m",
    "home_rotation_offense", "away_rotation_offense",
    "home_rotation_defense", "away_rotation_defense",
    "home_rotation_usage", "away_rotation_usage",
    "home_questionable_minutes", "away_questionable_minutes",
    "home_doubtful_count", "away_doubtful_count",
    "home_out_count", "away_out_count",
)


def _finite(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be numeric") from None
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _rotation_features(players: Iterable[RotationPlayer]) -> dict[str, float]:
    rows = list(players)
    if not rows:
        raise ValueError("V2 features require a projected rotation")
    minutes = sum(max(0.0, float(row.minutes)) for row in rows)
    if abs(minutes - 240.0) > 1.0:
        raise ValueError(f"V2 rotation minutes must sum to 240, got {minutes:.2f}")
    weighted_offense = sum(row.minutes * row.offensive_impact for row in rows) / 240.0
    weighted_defense = sum(row.minutes * row.defensive_impact for row in rows) / 240.0
    weighted_usage = sum(row.minutes * row.usage for row in rows) / 240.0
    questionable_minutes = sum(
        row.minutes for row in rows if str(row.status).upper() == "QUESTIONABLE"
    )
    doubtful_count = sum(str(row.status).upper() == "DOUBTFUL" for row in rows)
    out_count = sum(str(row.status).upper() == "OUT" for row in rows)
    return {
        "rotation_offense": weighted_offense,
        "rotation_defense": weighted_defense,
        "rotation_usage": weighted_usage,
        "questionable_minutes": questionable_minutes,
        "doubtful_count": float(doubtful_count),
        "out_count": float(out_count),
    }


def validate_feature_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != FEATURE_SCHEMA:
        raise ValueError("unrecognized V2 feature schema")
    features = payload.get("features")
    if not isinstance(features, dict):
        raise ValueError("V2 features must be an object")
    keys = tuple(features.keys())
    if set(keys) != set(FEATURE_NAMES):
        missing = sorted(set(FEATURE_NAMES) - set(keys))
        extra = sorted(set(keys) - set(FEATURE_NAMES))
        raise ValueError(f"V2 feature contract mismatch missing={missing} extra={extra}")
    for key in keys:
        lowered = key.lower()
        if any(token in lowered for token in FORBIDDEN_FEATURE_TOKENS):
            raise ValueError(f"market-derived V2 feature forbidden: {key}")
        _finite(features[key], key)
    return {
        "schema": FEATURE_SCHEMA,
        "features": {name: float(features[name]) for name in FEATURE_NAMES},
    }


def build_feature_snapshot(
    *,
    home: TeamMetrics,
    away: TeamMetrics,
    context: GameContext,
    home_rotation: Iterable[RotationPlayer],
    away_rotation: Iterable[RotationPlayer],
    score_projection: ScoreProjection | dict[str, Any],
) -> dict[str, Any]:
    """Build the exact pre-market training vector used by future V2 research."""
    home = home.validated()
    away = away.validated()
    if home.team != context.home or away.team != context.away:
        raise ValueError("V2 feature teams do not match game context")
    score = asdict(score_projection) if isinstance(score_projection, ScoreProjection) else dict(score_projection)
    hrot = _rotation_features(home_rotation)
    arot = _rotation_features(away_rotation)
    features = {
        "baseline_margin": score["margin_mean"],
        "baseline_total": score["total_mean"],
        "baseline_possessions": score["possessions"],
        "baseline_margin_sd": score["margin_sd"],
        "baseline_total_sd": score["total_sd"],
        "home_ortg": home.ortg, "away_ortg": away.ortg,
        "home_drtg": home.drtg, "away_drtg": away.drtg,
        "home_pace": home.pace, "away_pace": away.pace,
        "home_efg": home.efg, "away_efg": away.efg,
        "home_tov_pct": home.tov_pct, "away_tov_pct": away.tov_pct,
        "home_orb_pct": home.orb_pct, "away_orb_pct": away.orb_pct,
        "home_ft_rate": home.ft_rate, "away_ft_rate": away.ft_rate,
        "home_three_pa_rate": home.three_pa_rate,
        "away_three_pa_rate": away.three_pa_rate,
        "home_rim_rate": home.rim_rate, "away_rim_rate": away.rim_rate,
        "home_transition_rate": home.transition_rate,
        "away_transition_rate": away.transition_rate,
        "home_rest_days": context.home_rest_days,
        "away_rest_days": context.away_rest_days,
        "home_b2b": float(context.home_b2b), "away_b2b": float(context.away_b2b),
        "home_three_in_four": float(context.home_three_in_four),
        "away_three_in_four": float(context.away_three_in_four),
        "home_travel_km": context.home_travel_km,
        "away_travel_km": context.away_travel_km,
        "home_timezone_shift": context.home_timezone_shift,
        "away_timezone_shift": context.away_timezone_shift,
        "altitude_m": context.altitude_m,
        "home_rotation_offense": hrot["rotation_offense"],
        "away_rotation_offense": arot["rotation_offense"],
        "home_rotation_defense": hrot["rotation_defense"],
        "away_rotation_defense": arot["rotation_defense"],
        "home_rotation_usage": hrot["rotation_usage"],
        "away_rotation_usage": arot["rotation_usage"],
        "home_questionable_minutes": hrot["questionable_minutes"],
        "away_questionable_minutes": arot["questionable_minutes"],
        "home_doubtful_count": hrot["doubtful_count"],
        "away_doubtful_count": arot["doubtful_count"],
        "home_out_count": hrot["out_count"],
        "away_out_count": arot["out_count"],
    }
    return validate_feature_payload({"schema": FEATURE_SCHEMA, "features": features})
