"""Parity gate between canonical stats.nba.com and gamebook-derived stats.

A passing report makes the alternate source eligible for human review only.
It never changes provider authority, model generation, or betting certification.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from .rotation_projection import normalized_player_name
from .teams import canonical_team

TEAM_THRESHOLDS = {
    "OFF_RATING": 1.50,
    "DEF_RATING": 1.50,
    "PACE": 1.25,
    "EFG_PCT": 0.0125,
    "TM_TOV_PCT": 1.25,
    "OREB_PCT": 0.020,
}
PLAYER_MINUTES_MAE_MAX = 2.5
PLAYER_RECENT_MINUTES_MAE_MAX = 3.0
PLAYER_USAGE_MAE_MAX = 0.03
MIN_TEAM_COVERAGE = 25
MIN_PLAYER_OVERLAP = 100
MIN_GAMEBOOK_COMPLETENESS = 0.995
STYLE_THRESHOLDS = {
    "FT_RATE": 0.015,
    "THREE_PA_RATE": 0.015,
}


def _finite(value: Any, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be numeric") from None
    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be finite")
    return parsed


def _team_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        canonical_team(str(row.get("TEAM_NAME") or "")): row
        for row in rows
        if row.get("TEAM_NAME")
    }


def _player_map(rows: list[dict[str, Any]]) -> dict[tuple[int, str], dict[str, Any]]:
    result = {}
    for row in rows:
        if row.get("TEAM_ID") is None or not row.get("PLAYER_NAME"):
            continue
        result[(int(row["TEAM_ID"]), normalized_player_name(str(row["PLAYER_NAME"])))] = row
    return result


def _mae(values: list[float]) -> float | None:
    return sum(abs(value) for value in values) / len(values) if values else None


def _base_style_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for row in rows:
        name = canonical_team(str(row.get("TEAM_NAME") or ""))
        if not name:
            continue
        fga = _finite(row.get("FGA"), f"{name}.FGA")
        if fga <= 0:
            continue
        result[name] = {
            "FT_RATE": _finite(row.get("FTA"), f"{name}.FTA") / fga,
            "THREE_PA_RATE": _finite(row.get("FG3A"), f"{name}.FG3A") / fga,
        }
    return result


def assess(
    canonical: dict[str, Any],
    alternate: dict[str, Any],
) -> dict[str, Any]:
    if alternate.get("schema") != "pulsar-nba-gamebook-stat-pack-v1":
        raise ValueError("unsupported alternate stat-pack schema")
    if alternate.get("role") != "ALTERNATE_REFERENCE_ONLY":
        raise ValueError("alternate stat pack role is not reference-only")
    if alternate.get("source") != "NBA_OFFICIAL_SCORERS_REPORT":
        raise ValueError("alternate stat pack source mismatch")
    if alternate.get("production_provider_authorized") is not False:
        raise ValueError("alternate stat pack contains forbidden authority")
    if alternate.get("usage_scale") != "fraction_0_to_1":
        raise ValueError("alternate usage scale mismatch")
    if alternate.get("possession_method") != "symmetric_boxscore_estimate":
        raise ValueError("alternate possession method mismatch")
    if alternate.get("player_rating_method") != "team_efficiency_neutral_baseline":
        raise ValueError("alternate player rating method mismatch")
    for field in ("gamebook_manifest_sha256", "stat_pack_sha256"):
        value = str(alternate.get(field) or "")
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value.lower()):
            raise ValueError(f"alternate {field} missing or invalid")
    if canonical.get("season") != alternate.get("season"):
        raise ValueError("parity season mismatch")
    if canonical.get("date_to") != alternate.get("date_to"):
        raise ValueError("parity PIT cutoff mismatch")

    failures: list[str] = []
    completeness = _finite(
        alternate.get("gamebook_completeness", 0.0),
        "alternate.gamebook_completeness",
    )
    if completeness < MIN_GAMEBOOK_COMPLETENESS:
        failures.append(f"gamebook_completeness<{MIN_GAMEBOOK_COMPLETENESS}")
    windows: dict[str, Any] = {}
    for window in (0, 30, 15, 10, 5):
        canon_rows = _team_map((canonical.get("advanced_windows") or {}).get(window)
                               or (canonical.get("advanced_windows") or {}).get(str(window))
                               or [])
        alt_rows = _team_map((alternate.get("advanced_windows") or {}).get(window)
                             or (alternate.get("advanced_windows") or {}).get(str(window))
                             or [])
        overlap = sorted(set(canon_rows) & set(alt_rows))
        if len(overlap) < MIN_TEAM_COVERAGE:
            failures.append(f"window_{window}_team_overlap<{MIN_TEAM_COVERAGE}")
        metrics: dict[str, Any] = {}
        for metric, threshold in TEAM_THRESHOLDS.items():
            deltas = [
                _finite(alt_rows[team].get(metric), f"alternate.{team}.{metric}")
                - _finite(canon_rows[team].get(metric), f"canonical.{team}.{metric}")
                for team in overlap
            ]
            error = _mae(deltas)
            passed = error is not None and error <= threshold
            if not passed:
                failures.append(f"window_{window}_{metric}_mae>{threshold}")
            metrics[metric] = {
                "n": len(deltas),
                "mae": error,
                "threshold": threshold,
                "pass": passed,
            }
        windows[str(window)] = {
            "team_overlap": len(overlap),
            "metrics": metrics,
        }

    canonical_players = _player_map(canonical.get("player_season") or [])
    alternate_players = _player_map(alternate.get("player_season") or [])
    overlap_players = sorted(set(canonical_players) & set(alternate_players))
    if len(overlap_players) < MIN_PLAYER_OVERLAP:
        failures.append(f"player_overlap<{MIN_PLAYER_OVERLAP}")
    minute_deltas = [
        _finite(alternate_players[key].get("MIN"), "alternate.player.MIN")
        - _finite(canonical_players[key].get("MIN"), "canonical.player.MIN")
        for key in overlap_players
    ]
    minutes_mae = _mae(minute_deltas)
    if minutes_mae is None or minutes_mae > PLAYER_MINUTES_MAE_MAX:
        failures.append(f"player_minutes_mae>{PLAYER_MINUTES_MAE_MAX}")

    canonical_recent = _player_map(canonical.get("player_recent") or [])
    alternate_recent = _player_map(alternate.get("player_recent") or [])
    recent_overlap = sorted(set(canonical_recent) & set(alternate_recent))
    recent_minute_deltas = [
        _finite(alternate_recent[key].get("MIN"), "alternate.recent.MIN")
        - _finite(canonical_recent[key].get("MIN"), "canonical.recent.MIN")
        for key in recent_overlap
    ]
    recent_minutes_mae = _mae(recent_minute_deltas)
    if len(recent_overlap) < MIN_PLAYER_OVERLAP:
        failures.append(f"recent_player_overlap<{MIN_PLAYER_OVERLAP}")
    if recent_minutes_mae is None or recent_minutes_mae > PLAYER_RECENT_MINUTES_MAE_MAX:
        failures.append(
            f"recent_player_minutes_mae>{PLAYER_RECENT_MINUTES_MAE_MAX}"
        )

    canonical_advanced = _player_map(canonical.get("player_advanced") or [])
    alternate_advanced = _player_map(alternate.get("player_advanced") or [])
    usage_overlap = sorted(set(canonical_advanced) & set(alternate_advanced))
    usage_deltas = [
        _finite(alternate_advanced[key].get("USG_PCT"), "alternate.player.USG_PCT")
        - _finite(canonical_advanced[key].get("USG_PCT"), "canonical.player.USG_PCT")
        for key in usage_overlap
    ]
    usage_mae = _mae(usage_deltas)
    if len(usage_overlap) < MIN_PLAYER_OVERLAP:
        failures.append(f"usage_player_overlap<{MIN_PLAYER_OVERLAP}")
    if usage_mae is None or usage_mae > PLAYER_USAGE_MAE_MAX:
        failures.append(f"player_usage_mae>{PLAYER_USAGE_MAE_MAX}")

    canonical_style = _base_style_map(canonical.get("base_season") or [])
    alternate_style = _base_style_map(alternate.get("base_season") or [])
    style_overlap = sorted(set(canonical_style) & set(alternate_style))
    if len(style_overlap) < MIN_TEAM_COVERAGE:
        failures.append(f"base_style_team_overlap<{MIN_TEAM_COVERAGE}")
    style_metrics: dict[str, Any] = {}
    for metric, threshold in STYLE_THRESHOLDS.items():
        deltas = [
            alternate_style[team][metric] - canonical_style[team][metric]
            for team in style_overlap
        ]
        error = _mae(deltas)
        passed = error is not None and error <= threshold
        if not passed:
            failures.append(f"{metric}_mae>{threshold}")
        style_metrics[metric] = {
            "n": len(deltas),
            "mae": error,
            "threshold": threshold,
            "pass": passed,
        }

    # Player OFF/DEF ratings cannot be reproduced from final-box gamebooks
    # without inventing on/off possessions. Therefore this source can never
    # claim exact player-impact parity with the canonical advanced endpoint.
    limitations = [
        "player_off_def_ratings_use_team_neutral_baseline",
        "player_specific_rotation_impact_requires_fresh_prospective_validation",
    ]
    return {
        "schema": "pulsar-nba-gamebook-parity-v1",
        "role": "MANUAL_REVIEW_ONLY",
        "canonical_source": "stats.nba.com",
        "alternate_source": alternate.get("source"),
        "season": canonical.get("season"),
        "date_to": canonical.get("date_to"),
        "team_windows": windows,
        "gamebook_completeness": completeness,
        "minimum_gamebook_completeness": MIN_GAMEBOOK_COMPLETENESS,
        "player_overlap": len(overlap_players),
        "player_minutes_mae": minutes_mae,
        "recent_player_overlap": len(recent_overlap),
        "recent_player_minutes_mae": recent_minutes_mae,
        "usage_player_overlap": len(usage_overlap),
        "player_usage_mae": usage_mae,
        "base_style_team_overlap": len(style_overlap),
        "base_style_metrics": style_metrics,
        "limitations": limitations,
        "review_ready": not failures,
        "production_provider_authorized": False,
        "betting_certified": False,
        "failures": failures,
        "next_action": (
            "human review + freeze alternate provider generation + fresh prospective validation"
            if not failures
            else "keep gamebook source reference-only and collect/diagnose more parity evidence"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare canonical and gamebook-derived NBA stat packs")
    parser.add_argument("--canonical", required=True)
    parser.add_argument("--alternate", required=True)
    parser.add_argument("--output", default="runtime/gamebook_reference/parity.json")
    args = parser.parse_args()
    canonical = json.loads(Path(args.canonical).read_text(encoding="utf-8"))
    alternate = json.loads(Path(args.alternate).read_text(encoding="utf-8"))
    result = assess(canonical, alternate)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "review_ready": result["review_ready"],
        "production_provider_authorized": False,
        "failures": result["failures"],
    }, indent=2))


if __name__ == "__main__":
    main()
