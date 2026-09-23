"""Deterministic provenance of the predictive inputs; odds are NEVER model features."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable

from . import MODEL_GENERATION, PROBABILITY_POLICY_ID
from .model import GameContext, TeamMetrics
from .rotations import RotationPlayer

SCHEMA = "pulsar-nba-predictive-input-manifest-v1"
_SHA256 = re.compile(r"[a-fA-F0-9]{64}\Z")


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("provenance timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_input_manifest(
    *, context: GameContext, home: TeamMetrics, away: TeamMetrics,
    home_rotation: Iterable[RotationPlayer], away_rotation: Iterable[RotationPlayer],
    stats_snapshot_sha256: str, stats_observed_at: str,
    injury_snapshot_sha256: str, injury_reported_at: str,
) -> dict[str, Any]:
    """Bind stats AND injury versions, team strengths, minutes and game context.

    Caller must use the immutable SHA-256 returned by persist_snapshot, not
    a hash of arbitrary metadata. The manifest's SHA-256 identifies the exact
    inputs fed into the frozen basketball probability generation.
    """
    for name, value in (("stats_snapshot_sha256", stats_snapshot_sha256),
                        ("injury_snapshot_sha256", injury_snapshot_sha256)):
        if not _SHA256.fullmatch(str(value)):
            raise ValueError(f"invalid {name}")
    analysis = _utc(context.analyzed_at)
    stats_at, injury_at = _utc(stats_observed_at), _utc(injury_reported_at)
    if stats_at > analysis or injury_at > analysis:
        raise ValueError("predictive source was observed after the analysis")
    if home.team != context.home or away.team != context.away:
        raise ValueError("manifest team labels must match scheduled game")
    home_rot, away_rot = list(home_rotation), list(away_rotation)
    if not home_rot or not away_rot:
        raise ValueError("both input rotations are required")
    recorded = {
        "schema": SCHEMA,
        "model_generation": MODEL_GENERATION,
        "probability_policy_id": PROBABILITY_POLICY_ID,
        "game_id": context.game_id,
        "analyzed_at": context.analyzed_at,
        "stats_snapshot_sha256": stats_snapshot_sha256.lower(),
        "stats_observed_at": stats_observed_at,
        "injury_snapshot_sha256": injury_snapshot_sha256.lower(),
        "injury_reported_at": injury_reported_at,
        "game_context_sha256": _hash(asdict(context)),
        "home_team_sha256": _hash(asdict(home)),
        "away_team_sha256": _hash(asdict(away)),
        "home_rotation_sha256": _hash([asdict(player) for player in home_rot]),
        "away_rotation_sha256": _hash([asdict(player) for player in away_rot]),
    }
    recorded["source_snapshot_at"] = max(stats_at, injury_at).isoformat()
    recorded["sha256"] = _hash(recorded)
    return recorded


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema") != SCHEMA:
        raise ValueError("unrecognized input manifest schema")
    sha = manifest.get("sha256")
    if not _SHA256.fullmatch(str(sha)):
        raise ValueError("invalid manifest SHA-256")
    without_hash = {key: value for key, value in manifest.items() if key != "sha256"}
    if _hash(without_hash) != sha:
        raise ValueError("predictive input manifest checksum mismatch")
    if _utc(str(manifest["source_snapshot_at"])) > _utc(str(manifest["analyzed_at"])):
        raise ValueError("input manifest uses future data")
    if manifest.get("model_generation") != MODEL_GENERATION:
        raise ValueError("mixed predictive model generations")
    return manifest
