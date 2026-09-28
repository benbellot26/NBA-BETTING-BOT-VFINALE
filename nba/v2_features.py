"""Point-in-time feature contract for the learned V2 shadow.

Only basketball/context inputs are allowed here. Market/odds/price information is
explicitly forbidden from the training feature payload.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
import re
from typing import Any, Iterable

from .model import GameContext, ScoreProjection, TeamMetrics
from .rotations import RotationPlayer
from .teams import canonical_team

FEATURE_SCHEMA = "pulsar-nba-v2-features-v1"
_SHA256 = re.compile(r"[a-fA-F0-9]{64}\Z")
FORBIDDEN_FEATURE_TOKENS = (
    "odds", "market", "price", "book", "pinnacle", "sharp",
    "breakeven", "spread_line", "total_line",
)

TEMPORAL_WINDOWS = (
    ("season", 0),
    ("last30", 30),
    ("last15", 15),
    ("last10", 10),
    ("last5", 5),
)
TEMPORAL_METRICS = (
    ("ortg", "OFF_RATING"),
    ("drtg", "DEF_RATING"),
    ("pace", "PACE"),
)
TEMPORAL_FEATURE_NAMES = tuple(
    f"{side}_{metric}_{label}"
    for side in ("home", "away")
    for metric, _ in TEMPORAL_METRICS
    for label, _ in TEMPORAL_WINDOWS
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
) + TEMPORAL_FEATURE_NAMES


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


def _window_rows(
    advanced_windows: dict[Any, list[dict[str, Any]]] | None,
    window: int,
) -> list[dict[str, Any]]:
    if not advanced_windows:
        return []
    return list(
        advanced_windows.get(window)
        or advanced_windows.get(str(window))
        or []
    )


def _row_for_team(
    rows: list[dict[str, Any]], team_name: str,
) -> dict[str, Any] | None:
    target = canonical_team(team_name)
    for row in rows:
        if canonical_team(str(row.get("TEAM_NAME") or "")) == target:
            return row
    return None


def _temporal_features(
    side: str,
    team: TeamMetrics,
    advanced_windows: dict[Any, list[dict[str, Any]]] | None,
) -> dict[str, float]:
    """Expose raw season/recent windows so V2 can learn temporal weights.

    Missing recent windows fall back to the season row. If no raw pack is
    supplied (unit tests/offline compatibility), the already-PIT blended team
    metric is repeated rather than fabricating a new history.
    """
    fallback = {"ortg": team.ortg, "drtg": team.drtg, "pace": team.pace}
    season_row = _row_for_team(_window_rows(advanced_windows, 0), team.team)
    out: dict[str, float] = {}
    for metric, api_key in TEMPORAL_METRICS:
        season_default = (
            _finite(season_row.get(api_key), f"{side}_{metric}_season")
            if season_row is not None and season_row.get(api_key) is not None
            else float(fallback[metric])
        )
        for label, window in TEMPORAL_WINDOWS:
            row = season_row if window == 0 else _row_for_team(
                _window_rows(advanced_windows, window), team.team
            )
            raw = row.get(api_key) if row is not None else None
            value = season_default if raw is None else _finite(
                raw, f"{side}_{metric}_{label}"
            )
            out[f"{side}_{metric}_{label}"] = value
    return out


def _normalize_features(features: Any) -> dict[str, float]:
    if not isinstance(features, dict):
        raise ValueError("V2 features must be an object")
    keys = tuple(features.keys())
    if set(keys) != set(FEATURE_NAMES):
        missing = sorted(set(FEATURE_NAMES) - set(keys))
        extra = sorted(set(keys) - set(FEATURE_NAMES))
        raise ValueError(f"V2 feature contract mismatch missing={missing} extra={extra}")
    normalized: dict[str, float] = {}
    for key in keys:
        lowered = key.lower()
        if any(token in lowered for token in FORBIDDEN_FEATURE_TOKENS):
            raise ValueError(f"market-derived V2 feature forbidden: {key}")
        normalized[key] = _finite(features[key], key)
    return {name: normalized[name] for name in FEATURE_NAMES}


def _payload_digest(source_manifest_sha256: str, features: dict[str, float]) -> str:
    canonical = {
        "schema": FEATURE_SCHEMA,
        "source_manifest_sha256": source_manifest_sha256.lower(),
        "features": features,
    }
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def bind_feature_payload(
    features: dict[str, Any], *, source_manifest_sha256: str,
) -> dict[str, Any]:
    source = str(source_manifest_sha256 or "")
    if not _SHA256.fullmatch(source):
        raise ValueError("V2 features require a 64-character source manifest SHA-256")
    normalized = _normalize_features(features)
    digest = _payload_digest(source, normalized)
    return {
        "schema": FEATURE_SCHEMA,
        "source_manifest_sha256": source.lower(),
        "sha256": digest,
        "features": normalized,
    }


def validate_feature_payload(
    payload: dict[str, Any], *, require_bound: bool = False,
) -> dict[str, Any]:
    if payload.get("schema") != FEATURE_SCHEMA:
        raise ValueError("unrecognized V2 feature schema")
    normalized = _normalize_features(payload.get("features"))
    source = str(payload.get("source_manifest_sha256") or "")
    digest = str(payload.get("sha256") or "")
    if source:
        if not _SHA256.fullmatch(source):
            raise ValueError("invalid V2 source manifest SHA-256")
        expected = _payload_digest(source, normalized)
        if digest != expected:
            raise ValueError("V2 feature payload checksum mismatch")
    elif require_bound:
        raise ValueError("V2 feature payload is not bound to predictive lineage")
    if require_bound and not _SHA256.fullmatch(digest):
        raise ValueError("V2 feature payload checksum missing")
    return {
        "schema": FEATURE_SCHEMA,
        "source_manifest_sha256": source.lower() if source else None,
        "sha256": digest if digest else None,
        "features": normalized,
    }


def build_feature_snapshot(
    *,
    home: TeamMetrics,
    away: TeamMetrics,
    context: GameContext,
    home_rotation: Iterable[RotationPlayer],
    away_rotation: Iterable[RotationPlayer],
    score_projection: ScoreProjection | dict[str, Any],
    advanced_windows: dict[Any, list[dict[str, Any]]] | None = None,
    source_manifest_sha256: str,
) -> dict[str, Any]:
    """Build the exact pre-market training vector used by future V2 research."""
    home = home.validated()
    away = away.validated()
    if home.team != context.home or away.team != context.away:
        raise ValueError("V2 feature teams do not match game context")
    score = (
        asdict(score_projection)
        if isinstance(score_projection, ScoreProjection)
        else dict(score_projection)
    )
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
    features.update(_temporal_features("home", home, advanced_windows))
    features.update(_temporal_features("away", away, advanced_windows))
    return bind_feature_payload(
        features, source_manifest_sha256=source_manifest_sha256
    )
