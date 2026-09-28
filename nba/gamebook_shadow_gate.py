"""Manual review gate for the official-gamebook provider shadow.

Passing this gate never authorizes production use. It only means the collected
prospective evidence is sufficient for a human provider-review decision.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

MIN_RESOLVED = 250
MIN_PAIRED_V1 = 100
MAX_MARGIN_MAE_DEGRADATION = 0.15
MAX_TOTAL_MAE_DEGRADATION = 0.20
MAX_ML_BRIER_DEGRADATION = 0.005
MIN_COMPLETENESS = 1.0


def _num(value: Any, name: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be numeric") from None
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite")
    return out


def assess(
    report: dict[str, Any],
    *,
    minimum_resolved: int = MIN_RESOLVED,
    minimum_paired_v1: int = MIN_PAIRED_V1,
) -> dict[str, Any]:
    if report.get("schema") != "pulsar-nba-gamebook-provider-shadow-performance-v1":
        raise ValueError("unsupported gamebook provider shadow report")
    if report.get("role") != "MANUAL_REVIEW_ONLY":
        raise ValueError("provider shadow report role mismatch")
    for key in (
        "production_provider_authorized",
        "predictive_authority",
        "betting_certified",
        "review_ready",
    ):
        if report.get(key) is not False:
            raise ValueError(f"provider shadow report contains forbidden {key}=true state")

    failures: list[str] = []
    resolved = int(report.get("resolved_n") or 0)
    paired = int(report.get("paired_v1_n") or 0)
    if resolved < minimum_resolved:
        failures.append(f"resolved_n<{minimum_resolved}")
    if paired < minimum_paired_v1:
        failures.append(f"paired_v1_n<{minimum_paired_v1}")

    completeness = report.get("minimum_gamebook_completeness")
    if completeness is None or _num(completeness, "minimum_gamebook_completeness") < MIN_COMPLETENESS:
        failures.append("gamebook_completeness<1.0")

    comparisons: dict[str, Any] = {}
    specs = (
        (
            "margin_mae",
            "paired_shadow_margin_mae",
            "paired_v1_margin_mae",
            MAX_MARGIN_MAE_DEGRADATION,
        ),
        (
            "total_mae",
            "paired_shadow_total_mae",
            "paired_v1_total_mae",
            MAX_TOTAL_MAE_DEGRADATION,
        ),
        (
            "ml_brier",
            "paired_shadow_ml_brier",
            "paired_v1_ml_brier",
            MAX_ML_BRIER_DEGRADATION,
        ),
    )
    for label, shadow_key, v1_key, tolerance in specs:
        if report.get(shadow_key) is None or report.get(v1_key) is None:
            failures.append(f"{label}_paired_metric_missing")
            continue
        shadow = _num(report[shadow_key], shadow_key)
        champion = _num(report[v1_key], v1_key)
        delta = shadow - champion
        noninferior = delta <= tolerance
        if not noninferior:
            failures.append(f"{label}_degradation>{tolerance}")
        comparisons[label] = {
            "shadow": shadow,
            "v1": champion,
            "delta_shadow_minus_v1": delta,
            "tolerance": tolerance,
            "noninferior": noninferior,
            "improved": delta < 0,
        }

    return {
        "schema": "pulsar-nba-gamebook-provider-manual-review-v1",
        "role": "MANUAL_REVIEW_ONLY",
        "review_ready": not failures,
        "resolved_n": resolved,
        "minimum_resolved": minimum_resolved,
        "paired_v1_n": paired,
        "minimum_paired_v1": minimum_paired_v1,
        "comparisons": comparisons,
        "production_provider_authorized": False,
        "predictive_authority": False,
        "auto_promote": False,
        "betting_certified": False,
        "failures": failures,
        "next_action": (
            "human provider review + freeze a new provider generation + fresh prospective validation"
            if not failures
            else "keep provider shadow isolated and collect more paired evidence"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assess gamebook provider shadow for manual review readiness"
    )
    parser.add_argument(
        "--input",
        default="runtime/provider_shadow/performance.json",
    )
    parser.add_argument(
        "--output",
        default="runtime/provider_shadow/review_gate.json",
    )
    parser.add_argument("--minimum-resolved", type=int, default=MIN_RESOLVED)
    parser.add_argument("--minimum-paired-v1", type=int, default=MIN_PAIRED_V1)
    args = parser.parse_args()
    report = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = assess(
        report,
        minimum_resolved=args.minimum_resolved,
        minimum_paired_v1=args.minimum_paired_v1,
    )
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "review_ready": result["review_ready"],
        "resolved_n": result["resolved_n"],
        "paired_v1_n": result["paired_v1_n"],
        "auto_promote": False,
    }, indent=2))


if __name__ == "__main__":
    main()
