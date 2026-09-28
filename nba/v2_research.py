"""One-command orchestration for learned V2 research.

Exports immutable PIT replay evidence, selects only forecasts captured with the
learned feature contract, runs expanding-window evaluation and writes the manual
review gate. Nothing in this module can promote or certify a betting model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .replay_export import export as export_replay
from .v2_dataset import load_training_jsonl, manifest
from .v2_gate import assess
from .v2_walkforward import walk_forward


def run(
    *,
    forecasts: str = "runtime/evidence/final_forecasts.jsonl",
    outcomes: str = "runtime/evidence/final_outcomes.jsonl",
    dataset: str = "runtime/research/pit_dataset.jsonl",
    shadow_output: str = "runtime/research/v2_learned_shadow.json",
    gate_output: str = "runtime/research/v2_learned_gate.json",
    minimum_train: int = 400,
    minimum_holdout: int = 100,
    review_holdout: int = 250,
    step: int = 50,
) -> dict:
    replay_manifest = export_replay(
        forecasts_path=forecasts, outcomes_path=outcomes, output=dataset
    )
    rows = load_training_jsonl(dataset)
    learned_manifest = manifest(rows)
    manifest_path = Path(dataset).with_suffix(".v2-manifest.json")
    manifest_path.write_text(
        json.dumps(learned_manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    shadow = walk_forward(
        rows,
        minimum_train=minimum_train,
        minimum_holdout=minimum_holdout,
        step=step,
    )
    shadow_path = Path(shadow_output)
    shadow_path.parent.mkdir(parents=True, exist_ok=True)
    shadow_path.write_text(json.dumps(shadow, indent=2, sort_keys=True), encoding="utf-8")
    gate = assess(shadow, minimum_holdout=review_holdout)
    gate_path = Path(gate_output)
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(json.dumps(gate, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "role": "SHADOW",
        "replay": replay_manifest,
        "learned_dataset": learned_manifest,
        "holdout_n": shadow["holdout_shadow"]["n"],
        "review_ready": gate["review_ready"],
        "auto_promote": False,
        "betting_certified": False,
        "shadow_output": str(shadow_path),
        "gate_output": str(gate_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run learned NBA V2 PIT research")
    parser.add_argument("--forecasts", default="runtime/evidence/final_forecasts.jsonl")
    parser.add_argument("--outcomes", default="runtime/evidence/final_outcomes.jsonl")
    parser.add_argument("--dataset", default="runtime/research/pit_dataset.jsonl")
    parser.add_argument("--shadow-output", default="runtime/research/v2_learned_shadow.json")
    parser.add_argument("--gate-output", default="runtime/research/v2_learned_gate.json")
    parser.add_argument("--minimum-train", type=int, default=400)
    parser.add_argument("--minimum-holdout", type=int, default=100)
    parser.add_argument("--review-holdout", type=int, default=250)
    parser.add_argument("--step", type=int, default=50)
    args = parser.parse_args()
    result = run(
        forecasts=args.forecasts,
        outcomes=args.outcomes,
        dataset=args.dataset,
        shadow_output=args.shadow_output,
        gate_output=args.gate_output,
        minimum_train=args.minimum_train,
        minimum_holdout=args.minimum_holdout,
        review_holdout=args.review_holdout,
        step=args.step,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
