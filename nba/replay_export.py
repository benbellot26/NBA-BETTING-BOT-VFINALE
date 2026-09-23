"""Join immutable pre-tip FINAL forecasts to independently observed NBA results."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .v2_shadow import validate_row


def _read(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def join(forecasts: list[dict[str, Any]], outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for outcome in outcomes:
        key = str(outcome["game_id"])
        if key in results:
            raise ValueError("duplicate independently settled game")
        if outcome.get("source") != "official_nba_schedule":
            raise ValueError("unverified outcome provenance")
        results[key] = outcome
    seen: set[tuple[str, str]] = set()
    rows = []
    for forecast in forecasts:
        key = (str(forecast["game_id"]), str(forecast["model_generation"]))
        if key in seen:
            raise ValueError("duplicate FINAL forecast for game and generation")
        seen.add(key)
        if key[0] not in results:
            continue
        result = results[key[0]]
        row = {
            "game_id": key[0],
            "model_generation": key[1],
            "source_snapshot_sha256": forecast["source_snapshot_sha256"],
            "source_snapshot_at": forecast["source_snapshot_at"],
            "forecast_at": forecast["forecast_at"],
            "tipoff_at": forecast["tipoff_at"],
            "baseline_margin": forecast["baseline_margin"],
            "baseline_total": forecast["baseline_total"],
            "baseline_margin_sd": forecast["baseline_margin_sd"],
            "baseline_total_sd": forecast["baseline_total_sd"],
            "outcome_at": result["outcome_at"],
            "home_score": result["home_score"],
            "away_score": result["away_score"],
        }
        rows.append(validate_row(row))
    rows.sort(key=lambda row: (row["tipoff_at"], row["game_id"]))
    return rows


def export(*, forecasts_path: str, outcomes_path: str,
           output: str = "runtime/research/pit_dataset.jsonl") -> dict[str, Any]:
    data = join(_read(forecasts_path), _read(outcomes_path))
    if not data:
        raise RuntimeError("no settled PIT FINAL forecasts; refusing to generate empty training data")
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                      for row in data)
    target.write_text(content, encoding="utf-8")
    manifest = {
        "schema": "pulsar-nba-pit-replay-v1", "n": len(data),
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "first_tipoff": data[0]["tipoff_at"], "last_tipoff": data[-1]["tipoff_at"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "no_market_features": True, "requires_chronological_split": True,
    }
    target.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forecasts", default="runtime/evidence/final_forecasts.jsonl")
    parser.add_argument("--outcomes", default="runtime/evidence/final_outcomes.jsonl")
    parser.add_argument("--output", default="runtime/research/pit_dataset.jsonl")
    args = parser.parse_args()
    print(json.dumps(export(forecasts_path=args.forecasts, outcomes_path=args.outcomes,
                            output=args.output), indent=2))


if __name__ == "__main__":
    main()
