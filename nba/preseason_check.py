"""Preseason software readiness: offline-only, zero odds requests or wagers."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from . import MODEL_GENERATION, PROBABILITY_POLICY_ID, ROLE, VERSION
from .e2e_dryrun import run as e2e_run
from .preflight import run as preflight_run

WORKFLOWS = (
    ".github/workflows/live-research.yml",
    ".github/workflows/daily-evidence.yml",
)
DATA_RUNNER_WORKFLOWS = WORKFLOWS + (".github/workflows/provider-smoke.yml",)

MARKETS = ("ML", "SPREAD", "TOTAL")


def check(*, root: str | Path = ".") -> dict[str, Any]:
    """Check code integrity, fixture integration and static fail-closed guards.

    This NEVER calls the NBA websites, Odds API, GitHub secrets or a scheduler.
    Actual GitHub repository variables and upstream accessibility are not
    verifiable from a checked-out source tree.
    """
    directory = Path(root)
    errors: list[str] = []
    preflight = preflight_run()
    if not preflight["ok"]:
        errors.extend(preflight["failures"])
    try:
        fixture = e2e_run()
        if fixture["role"] != "SYNTHETIC_CI_ONLY":
            errors.append("e2e fixture has an unexpected role")
        if fixture["bet_count"] != 0 or fixture["candidate_count"] < 6:
            errors.append("e2e fixture did not produce six uncertified candidates")
        if not fixture["rotations_240"] or not fixture["all_probabilities_valid"]:
            errors.append("e2e rotations or probability validation failed")
    except Exception as exc:
        fixture = None
        errors.append(f"e2e:{type(exc).__name__}:{exc}")

    try:
        certificate = json.loads(
            (directory / "data/nba_betting_certification.json").read_text(encoding="utf-8"))
        locked = (
            ROLE == "RESEARCH"
            and certificate.get("certified") is False
            and certificate.get("approved_for_live") is not True
            and certificate.get("model_generation") == MODEL_GENERATION
            and certificate.get("probability_policy_id") == PROBABILITY_POLICY_ID
            and all(
                (certificate.get("markets") or {}).get(name, {}).get("betting_certified") is False
                for name in MARKETS
            )
        )
        if not locked:
            errors.append("source-controlled betting certification is not locked")
    except (OSError, ValueError, TypeError) as exc:
        locked = False
        errors.append(f"certification_file:{type(exc).__name__}")

    gate = True
    for relative in WORKFLOWS:
        try:
            content = (directory / relative).read_text(encoding="utf-8")
            if "NBA_LIVE_ENABLED == 'true'" not in content:
                gate = False
                errors.append(f"missing live gate: {relative}")
        except OSError:
            gate = False
            errors.append(f"missing workflow: {relative}")

    portable_runner = True
    for relative in DATA_RUNNER_WORKFLOWS:
        try:
            content = (directory / relative).read_text(encoding="utf-8")
            if "vars.NBA_DATA_RUNNER" not in content or "ubuntu-latest" not in content:
                portable_runner = False
                errors.append(f"missing configurable NBA data runner: {relative}")
        except OSError:
            portable_runner = False
            if f"missing workflow: {relative}" not in errors:
                errors.append(f"missing workflow: {relative}")

    safe_manual_preseason = True
    try:
        live_workflow = (directory / ".github/workflows/live-research.yml").read_text(
            encoding="utf-8")
        required_fragments = (
            "github.event_name == 'workflow_dispatch'",
            "inputs.operating_mode == 'preseason'",
            'type: choice',
            'default: preseason',
            'Regular research requires NBA_LIVE_ENABLED=true.',
        )
        if not all(fragment in live_workflow for fragment in required_fragments):
            safe_manual_preseason = False
            errors.append("manual preseason dispatch safety gate is missing")
    except OSError:
        safe_manual_preseason = False

    return {
        "schema": "pulsar-nba-preseason-software-check-v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "version": VERSION,
        "model_generation": MODEL_GENERATION,
        "role": "PRESEASON_SOFTWARE_RESEARCH",
        "software_ready": not errors,
        "live_operational": False,
        "real_betting_authorized": False,
        "upstream_providers": "NOT_TESTED_IN_OFFLINE_CHECK",
        "actual_github_variable": "NOT_READ",
        "odds_api_requests": 0,
        "checks": {
            "preflight_ok": preflight["ok"],
            "modules_checked": preflight["modules_checked"],
            "synthetic_e2e_ok": fixture is not None and fixture.get("bet_count") == 0,
            "synthetic_candidate_count": fixture.get("candidate_count") if fixture else 0,
            "source_certification_locked": locked,
            "live_workflow_gate_present": gate,
            "data_runner_portable": portable_runner,
            "safe_manual_preseason_dispatch": safe_manual_preseason,
        },
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline preseason software check: no network or odds credits")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", help="Optional JSON report destination")
    args = parser.parse_args()
    report = check(root=args.root)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["software_ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
