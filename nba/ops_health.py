"""Operational health summary. Reporting only; never authorizes wagering."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def _json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def build(*, root: str | Path = "runtime") -> dict[str, Any]:
    base = Path(root)
    live = _json(base / "live_run.json")
    provider = _json(base / "health/provider_smoke.json")
    odds = _json(base / "health/odds_market_smoke.json")
    audit = _json(base / "evidence/audit.json")
    performance = _json(base / "evidence/performance.json")
    certification = _json(base / "evidence/certification_candidate.json")
    forecast_count = int((audit or {}).get("counts", {}).get("final_forecasts") or 0)
    paper_count = int((audit or {}).get("counts", {}).get("paper_entries") or 0)
    settled_count = int((audit or {}).get("counts", {}).get("settled_entries") or 0)
    provider_ok = (provider or {}).get("ok") is True
    odds_ok = (odds or {}).get("coverage_ok") is True
    audit_ok = (audit or {}).get("ok") is True if audit is not None else None
    return {
        "schema": "pulsar-nba-ops-health-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "software_state": "READY_BY_CI",
        "provider_state": "GREEN" if provider_ok else ("UNKNOWN" if provider is None else "RED"),
        "odds_state": "GREEN" if odds_ok else ("UNKNOWN" if odds is None else "RED"),
        "last_session_state": (live or {}).get("status", "UNKNOWN"),
        "last_session_mode": (live or {}).get("mode"),
        "evidence_state": {
            "audit_ok": audit_ok,
            "final_forecasts": forecast_count,
            "paper_entries": paper_count,
            "settled_entries": settled_count,
            "performance_games": int((performance or {}).get("games") or 0),
        },
        "source_certification_candidate": {
            "certified": bool((certification or {}).get("certified") is True),
            "approved_for_live": bool((certification or {}).get("approved_for_live") is True),
        },
        "rehearsal_ready": provider_ok and odds_ok,
        "live_operational": False,
        "real_betting_authorized": False,
        "notes": [
            "Provider/odds health must be observed on the intended runner.",
            "A green health report is not profitability evidence or live betting approval.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="runtime")
    parser.add_argument("--output", default="runtime/health/summary.json")
    args = parser.parse_args()
    report = build(root=args.root)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
