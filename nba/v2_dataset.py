"""Validated point-in-time dataset contract for learned V2 research."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from .v2_features import FEATURE_NAMES, FEATURE_SCHEMA, validate_feature_payload
from .v2_shadow import validate_row as validate_legacy_row

DATASET_SCHEMA = "pulsar-nba-v2-training-row-v1"


def _dt(value: str) -> datetime:
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("V2 dataset timestamps require timezone")
    return result.astimezone(timezone.utc)


def _finite(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be numeric") from None
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def validate_evaluation_only(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("evaluation_only must be an object")
    out: dict[str, Any] = {}
    if value.get("spread_line") is not None:
        out["spread_line"] = _finite(value["spread_line"], "spread_line")
    if value.get("total_line") is not None:
        out["total_line"] = _finite(value["total_line"], "total_line")
    sharp = value.get("pinnacle_entry_probability")
    if sharp is not None:
        if not isinstance(sharp, dict):
            raise ValueError("pinnacle_entry_probability must be an object")
        parsed: dict[str, float] = {}
        for market in ("ML", "SPREAD", "TOTAL"):
            if sharp.get(market) is None:
                continue
            p = _finite(sharp[market], f"pinnacle_entry_probability.{market}")
            if not 0.0 <= p <= 1.0:
                raise ValueError("Pinnacle evaluation probability outside [0,1]")
            parsed[market] = p
        out["pinnacle_entry_probability"] = parsed
    return out


def validate_training_row(row: dict[str, Any]) -> dict[str, Any]:
    """Validate labels, PIT ordering and the strict training/evaluation boundary."""
    clean = validate_legacy_row(row)
    features = validate_feature_payload(row.get("v2_features") or {})
    clean["v2_features"] = features
    clean["evaluation_only"] = validate_evaluation_only(row.get("evaluation_only"))
    clean["dataset_schema"] = DATASET_SCHEMA
    # The only training inputs are the versioned feature payload. Evaluation
    # metadata may contain market lines/sharp probabilities but is never exposed
    # by feature_vector().
    if _dt(clean["source_snapshot_at"]) > _dt(clean["forecast_at"]):
        raise ValueError("V2 source snapshot occurs after forecast")
    return clean


def feature_vector(row: dict[str, Any]) -> list[float]:
    clean = validate_training_row(row)
    values = clean["v2_features"]["features"]
    return [float(values[name]) for name in FEATURE_NAMES]


def targets(row: dict[str, Any]) -> tuple[float, float]:
    clean = validate_training_row(row)
    home = float(clean["home_score"])
    away = float(clean["away_score"])
    return home - away, home + away


def load_training_jsonl(path: str | Path) -> list[dict[str, Any]]:
    raw = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    # Forecasts captured before the learned-feature contract was introduced
    # remain valid legacy V1 evidence, but cannot be reconstructed into V2
    # training rows after the fact. Exclude them explicitly rather than
    # fabricating historical features.
    eligible = [row for row in raw if row.get("v2_features") is not None]
    if not eligible:
        raise ValueError("no forecasts contain the learned V2 feature contract")
    rows = [validate_training_row(row) for row in eligible]
    if len({str(row["game_id"]) for row in rows}) != len(rows):
        raise ValueError("duplicate game IDs in learned V2 dataset")
    return sorted(rows, key=lambda row: (_dt(row["forecast_at"]), str(row["game_id"])))


def dataset_fingerprint(rows: Iterable[dict[str, Any]]) -> str:
    records = []
    for row in rows:
        clean = validate_training_row(row)
        records.append({
            "game_id": clean["game_id"],
            "snapshot": clean["source_snapshot_sha256"],
            "forecast_at": clean["forecast_at"],
            "outcome_at": clean["outcome_at"],
            "features": clean["v2_features"]["features"],
            "home_score": clean["home_score"],
            "away_score": clean["away_score"],
        })
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def manifest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot create V2 manifest for empty dataset")
    validated = [validate_training_row(row) for row in rows]
    return {
        "schema": "pulsar-nba-v2-dataset-manifest-v1",
        "feature_schema": FEATURE_SCHEMA,
        "feature_count": len(FEATURE_NAMES),
        "n": len(validated),
        "fingerprint": dataset_fingerprint(validated),
        "first_forecast": min(row["forecast_at"] for row in validated),
        "last_forecast": max(row["forecast_at"] for row in validated),
        "training_inputs": "v2_features_only",
        "evaluation_only_excluded_from_training": True,
    }
