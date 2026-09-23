"""One resilient NBA research/rehearsal session with a health artifact."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .close_runtime import capture as capture_close
from .live_runtime import run as run_live
from .ops_health import build as build_health


def run(*, target_date: str, mode: str = "regular",
        runtime_root: str = "runtime") -> dict:
    root = Path(runtime_root)
    live_path = root / "live_run.json"
    paper = root / "evidence/paper_entries.jsonl"
    forecasts = root / "evidence/final_forecasts.jsonl"
    live = run_live(
        target_date=target_date, output=str(live_path),
        snapshot_root=str(root / "snapshots"),
        paper_path=str(paper), forecasts_path=str(forecasts), mode=mode,
    )
    close = {"added": 0, "pending": 0, "failures": [], "skipped": True}
    if mode == "regular" and live.get("status") == "OK":
        close = capture_close(
            paper_path=str(paper),
            close_path=str(root / "evidence/close_ledger.jsonl"),
            mode="live",
        )
        close["skipped"] = False
    report = {
        "schema": "pulsar-nba-research-session-v1",
        "target_date": target_date,
        "mode": mode,
        "live": {
            "status": live.get("status"),
            "games": len(live.get("games") or []),
            "failures": live.get("failures") or [],
            "evidence_eligible": live.get("evidence_eligible"),
        },
        "close": close,
        "real_betting_authorized": False,
    }
    session_path = root / "health/session.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    health = build_health(root=root)
    (root / "health/summary.json").write_text(json.dumps(health, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(ZoneInfo("America/New_York")).date().isoformat())
    parser.add_argument("--mode", choices=("regular", "preseason"), default="regular")
    parser.add_argument("--runtime-root", default="runtime")
    args = parser.parse_args()
    print(json.dumps(run(target_date=args.date, mode=args.mode,
                         runtime_root=args.runtime_root), indent=2))


if __name__ == "__main__":
    main()
