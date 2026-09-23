"""Manual-review gate for the V2 shadow. Never promotes code or certifies betting."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

MIN_HOLDOUT = 250
MAX_BRIER_DEGRADATION = 0.002
MAX_LOGLOSS_DEGRADATION = 0.005
MAX_ECE_DEGRADATION = 0.01
MAX_MAE_DEGRADATION = 0.10
MIN_KEY_IMPROVEMENTS = 2

METRICS = (
    ("ml_brier", "lower", MAX_BRIER_DEGRADATION),
    ("ml_logloss", "lower", MAX_LOGLOSS_DEGRADATION),
    ("ml_ece", "lower", MAX_ECE_DEGRADATION),
    ("margin_mae", "lower", MAX_MAE_DEGRADATION),
    ("total_mae", "lower", MAX_MAE_DEGRADATION),
)


def _finite_number(value: Any, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be numeric") from None
    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be finite")
    return parsed


def assess(report: dict[str, Any], *, minimum_holdout: int = MIN_HOLDOUT) -> dict[str, Any]:
    if report.get("role") != "SHADOW":
        raise ValueError("only SHADOW reports can enter V2 review")
    if report.get("promoted") is not False or report.get("auto_betting_certification") is not False:
        raise ValueError("shadow report contains forbidden automatic promotion state")
    champion = report.get("holdout_champion") or {}
    challenger = report.get("holdout_shadow") or {}
    champion_n = int(champion.get("n") or 0)
    challenger_n = int(challenger.get("n") or 0)
    failures: list[str] = []
    if champion_n != challenger_n:
        failures.append("paired_holdout_size_mismatch")
    if challenger_n < minimum_holdout:
        failures.append(f"holdout_n<{minimum_holdout}")
    comparisons: dict[str, Any] = {}
    strict_improvements = 0
    for metric, direction, tolerance in METRICS:
        base = _finite_number(champion.get(metric), f"champion.{metric}")
        shadow = _finite_number(challenger.get(metric), f"shadow.{metric}")
        delta = shadow - base
        noninferior = delta <= tolerance
        improved = delta < 0
        if improved:
            strict_improvements += 1
        if not noninferior:
            failures.append(f"{metric}_degradation>{tolerance}")
        comparisons[metric] = {
            "champion": base, "shadow": shadow,
            "delta_shadow_minus_champion": delta,
            "noninferior": noninferior, "improved": improved,
        }
    if strict_improvements < MIN_KEY_IMPROVEMENTS:
        failures.append(f"strict_improvements<{MIN_KEY_IMPROVEMENTS}")
    return {
        "schema": "pulsar-nba-v2-manual-review-v1",
        "role": "MANUAL_REVIEW_ONLY",
        "review_ready": not failures,
        "auto_promote": False,
        "betting_certified": False,
        "holdout_n": challenger_n,
        "minimum_holdout": minimum_holdout,
        "strict_improvements": strict_improvements,
        "comparisons": comparisons,
        "failures": failures,
        "next_action": (
            "human code review + new frozen generation + new prospective validation"
            if not failures else "keep V2 in shadow and collect/diagnose more evidence"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Assess NBA V2 shadow for manual review readiness")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="runtime/research/v2_manual_review.json")
    parser.add_argument("--minimum-holdout", type=int, default=MIN_HOLDOUT)
    args = parser.parse_args()
    report = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = assess(report, minimum_holdout=args.minimum_holdout)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "review_ready": result["review_ready"],
        "auto_promote": False,
        "holdout_n": result["holdout_n"],
        "failures": result["failures"],
    }, indent=2))


if __name__ == "__main__":
    main()
