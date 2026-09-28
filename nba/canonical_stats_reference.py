"""Independent canonical stats.nba.com capture for gamebook parity research.

This module is deliberately isolated from live prediction. It performs no odds
requests, does not read injury reports, and cannot authorize a provider or bet.
Its only purpose is to persist a canonical PIT stat pack whenever the configured
runner can reach stats.nba.com, then compare it with the official-gamebook
alternate source on the exact same cutoff.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .gamebook_parity import assess as assess_gamebook_parity
from .live_inputs import acquire_stat_pack
from .schedule import season_for_date

STATUS_SCHEMA = "pulsar-nba-canonical-stats-reference-status-v1"
REFERENCE_ROLE = "CANONICAL_PARITY_REFERENCE_ONLY"


def _json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _classify(exc: Exception) -> str:
    message = str(exc).lower()
    if "http 401" in message or "http 403" in message:
        return "ACCESS_BLOCKED"
    if "timeout" in message:
        return "TIMEOUT"
    if (
        "not yet sufficiently available" in message
        or "no backfill from future" in message
        or "unexpected team-stat row count current=0" in message
    ):
        return "WAITING_FOR_SEASON_DATA"
    return "UNAVAILABLE"


def _write(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _read(path: str | Path) -> dict[str, Any] | None:
    target = Path(path)
    if not target.exists():
        return None
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _reference_pack(pack: dict[str, Any]) -> dict[str, Any]:
    required = (
        "season", "date_to", "observed_at", "advanced_windows",
        "base_season", "player_season", "player_recent", "player_advanced",
    )
    missing = [key for key in required if key not in pack]
    if missing:
        raise ValueError(f"canonical stat pack missing fields: {missing}")
    result = {
        key: pack[key] for key in required
    }
    result.update({
        "schema": "pulsar-nba-canonical-stat-pack-v1",
        "role": REFERENCE_ROLE,
        "source": "stats.nba.com",
        "production_provider_authorized": False,
        "predictive_authority": False,
        "betting_certified": False,
        "source_snapshot": pack.get("snapshot"),
    })
    result["stat_pack_sha256"] = _json_sha256(result)
    return result


def run(
    *,
    target_date: str,
    output: str = "runtime/canonical_stats_reference/stat_pack.json",
    status_output: str = "runtime/canonical_stats_reference/status.json",
    parity_output: str = "runtime/gamebook_reference/parity.json",
    alternate_path: str = "runtime/gamebook_reference/stat_pack.json",
    snapshot_root: str = "runtime/canonical_stats_reference/snapshots",
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    season = season_for_date(target_date)
    status: dict[str, Any] = {
        "schema": STATUS_SCHEMA,
        "role": REFERENCE_ROLE,
        "checked_at": now.isoformat(),
        "target_date": target_date,
        "season": season,
        "state": "STARTED",
        "canonical_pack_available": False,
        "parity_attempted": False,
        "parity_review_ready": False,
        "production_provider_authorized": False,
        "predictive_authority": False,
        "betting_certified": False,
        "odds_api_requests": 0,
    }
    try:
        observed_at = datetime.now(timezone.utc).isoformat()
        pack = acquire_stat_pack(
            season=season,
            observed_at=observed_at,
            game_date=target_date,
            snapshot_root=snapshot_root,
        )
        reference = _reference_pack(pack)
        _write(output, reference)
        status.update({
            "state": "READY_FOR_PARITY",
            "canonical_pack_available": True,
            "date_to": reference["date_to"],
            "team_rows": len(
                (reference.get("advanced_windows") or {}).get(0)
                or (reference.get("advanced_windows") or {}).get("0")
                or []
            ),
            "player_rows": len(reference.get("player_season") or []),
            "stat_pack_sha256": reference["stat_pack_sha256"],
        })

        alternate = _read(alternate_path)
        if alternate is None:
            status["parity_state"] = "ALTERNATE_PACK_MISSING"
        elif (
            alternate.get("season") != reference.get("season")
            or alternate.get("date_to") != reference.get("date_to")
        ):
            status["parity_state"] = "CUTOFF_MISMATCH"
            status["alternate_season"] = alternate.get("season")
            status["alternate_date_to"] = alternate.get("date_to")
        else:
            status["parity_attempted"] = True
            parity = assess_gamebook_parity(reference, alternate)
            _write(parity_output, parity)
            status["parity_state"] = "COMPARED"
            status["parity_review_ready"] = bool(parity.get("review_ready"))
            status["parity_failures"] = parity.get("failures") or []
    except Exception as exc:
        state = _classify(exc)
        status.update({
            "state": state,
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
    _write(status_output, status)
    return status


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture canonical stats.nba.com pack for gamebook parity"
    )
    eastern_today = datetime.now(
        ZoneInfo("America/New_York")
    ).date().isoformat()
    parser.add_argument("--date", default=eastern_today)
    parser.add_argument(
        "--output",
        default="runtime/canonical_stats_reference/stat_pack.json",
    )
    parser.add_argument(
        "--status",
        default="runtime/canonical_stats_reference/status.json",
    )
    parser.add_argument(
        "--alternate",
        default="runtime/gamebook_reference/stat_pack.json",
    )
    parser.add_argument(
        "--parity-output",
        default="runtime/gamebook_reference/parity.json",
    )
    parser.add_argument(
        "--snapshot-root",
        default="runtime/canonical_stats_reference/snapshots",
    )
    args = parser.parse_args()
    result = run(
        target_date=args.date,
        output=args.output,
        status_output=args.status,
        parity_output=args.parity_output,
        alternate_path=args.alternate,
        snapshot_root=args.snapshot_root,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
