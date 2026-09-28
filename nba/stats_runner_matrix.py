"""Aggregate cross-runner NBA stats transport diagnostics.

Each runner executes the same NETWORK_DIAGNOSTIC_ONLY route probe. This module
merges those independent artifacts without granting provider authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


EXPECTED_RUNNERS = ("ubuntu-latest", "windows-latest", "macos-latest")


def merge(directory: str | Path) -> dict[str, Any]:
    root = Path(directory)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(root.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(value, dict):
            continue
        if value.get("schema") != "pulsar-nba-stats-route-transport-v1":
            continue
        runner = str(value.get("runner") or "").strip()
        if runner not in EXPECTED_RUNNERS or runner in seen:
            continue
        seen.add(runner)
        rows.append(value)

    by_runner = {str(row["runner"]): row for row in rows}
    summaries: dict[str, Any] = {}
    working: list[str] = []
    alternate_working: list[str] = []
    for runner in EXPECTED_RUNNERS:
        row = by_runner.get(runner)
        if row is None:
            summaries[runner] = {"state": "MISSING_ARTIFACT", "valid_stats_routes": []}
            continue
        valid = list(row.get("valid_stats_routes") or [])
        if valid:
            working.append(runner)
        if row.get("alternate_official_route_found") is True:
            alternate_working.append(runner)
        summaries[runner] = {
            "state": "VALID_ROUTE_FOUND" if valid else "NO_VALID_ROUTE",
            "valid_stats_routes": valid,
            "alternate_official_route_found": bool(row.get("alternate_official_route_found")),
            "routes": [
                {
                    "name": item.get("name"),
                    "state": item.get("state"),
                    "elapsed_ms": item.get("elapsed_ms"),
                    "rows": item.get("rows"),
                }
                for item in (row.get("routes") or [])
            ],
        }

    return {
        "schema": "pulsar-nba-stats-runner-matrix-v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "role": "NETWORK_DIAGNOSTIC_ONLY",
        "expected_runners": list(EXPECTED_RUNNERS),
        "received_runners": sorted(seen),
        "working_runners": working,
        "alternate_route_working_runners": alternate_working,
        "hosted_runner_solution_found": bool(working),
        "predictive_evidence_eligible": False,
        "production_provider_authorized": False,
        "odds_api_requests": 0,
        "runners": summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge NBA stats cross-runner probes")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", default="runtime/stats_runner_matrix.json")
    args = parser.parse_args()
    result = merge(args.input_dir)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
