"""Read-only, fail-closed audit of prospective NBA research evidence.

An audit pass checks internal consistency; it NEVER certifies profitability,
provider authenticity, or the validity of a manually fabricated timestamp.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Iterable

from .lineage import validate_manifest
from .model import ProbabilitySurface
from .settlement import settle_candidate

SCHEMA = "pulsar-nba-evidence-audit-v1"


def _dt(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("missing timestamp timezone")
    return parsed.astimezone(timezone.utc)


def _read(path: str) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _index(rows: Iterable[dict[str, Any]], name: str,
           errors: list[str]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("entry_key") or row.get("game_id") or "")
        if not key:
            errors.append(f"{name}:missing_key")
        elif key in indexed:
            errors.append(f"{name}:{key}:duplicate_key")
        else:
            indexed[key] = row
    return indexed


def audit_records(
    *, forecasts: list[dict[str, Any]], outcomes: list[dict[str, Any]],
    paper: list[dict[str, Any]], closes: list[dict[str, Any]],
    settled: list[dict[str, Any]], at: str | None = None,
) -> dict[str, Any]:
    now = _dt(at) if at else datetime.now(timezone.utc)
    errors: list[str] = []
    warnings: list[str] = []
    f = _index(forecasts, "forecast", errors)
    o = _index(outcomes, "outcome", errors)
    p = _index(paper, "paper", errors)
    c = _index(closes, "close", errors)
    s = _index(settled, "settled", errors)
    by_game: dict[str, dict[str, Any]] = {}
    for key, row in f.items():
        try:
            manifest = validate_manifest(row["input_manifest"])
            probabilities = row["probabilities"]
            if not isinstance(probabilities, dict):
                raise ValueError("missing complete probability surface")
            ProbabilitySurface(**probabilities).validated()
            if row["role"] != "PIT_FINAL_FORECAST":
                raise ValueError("wrong prospective cohort role")
            if (str(row["game_id"]) != str(manifest["game_id"])
                    or str(row["model_generation"]) != str(manifest["model_generation"])
                    or row["source_snapshot_sha256"] != manifest["sha256"]
                    or _dt(row["source_snapshot_at"]) != _dt(manifest["source_snapshot_at"])
                    or _dt(row["forecast_at"]) != _dt(manifest["analyzed_at"])):
                raise ValueError("forecast and input manifest do not match")
            forecast = _dt(row["forecast_at"])
            tip = _dt(row["tipoff_at"])
            if _dt(row["source_snapshot_at"]) > forecast or forecast >= tip:
                raise ValueError("predictive information was not pre-tip")
            remaining = (tip - forecast).total_seconds() / 60
            if not 5 <= remaining <= 30:
                raise ValueError("forecast outside FINAL 5-30 minute cohort")
            game = str(row["game_id"])
            if game in by_game:
                raise ValueError("duplicate game across model generations in same evidence cohort")
            by_game[game] = row
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"forecast:{key}:{exc}")
    for key, row in o.items():
        try:
            if row.get("source") != "official_nba_schedule":
                raise ValueError("unverified outcome source")
            if str(row.get("game_id")) != key:
                raise ValueError("outcome key mismatch")
            home, away = float(row["home_score"]), float(row["away_score"])
            if any(not math.isfinite(x) or x < 0 or not x.is_integer()
                   for x in (home, away)):
                raise ValueError("invalid final score")
            forecast = by_game.get(key)
            if forecast and _dt(row["outcome_at"]) <= _dt(forecast["tipoff_at"]):
                raise ValueError("outcome observed before the game")
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"outcome:{key}:{exc}")
    for key, row in p.items():
        try:
            game = str(row["game_id"])
            forecast = by_game.get(game)
            if forecast is None:
                raise ValueError("paper selection lacks an audited full-game forecast")
            if row.get("status") != "PAPER" or row.get("phase") != "FINAL":
                raise ValueError("paper entry has invalid role or phase")
            if row.get("model_generation") != forecast["model_generation"]:
                raise ValueError("paper and forecast model generations differ")
            manifest = validate_manifest(row["input_manifest"])
            if (manifest["game_id"] != game
                    or manifest["model_generation"] != forecast["model_generation"]
                    or row.get("source_snapshot_sha256") != manifest["sha256"]
                    or _dt(row["entry_at"]) != _dt(manifest["analyzed_at"])
                    or _dt(row["source_snapshot_at"]) != _dt(manifest["source_snapshot_at"])):
                raise ValueError("paper predictive input manifest does not match")
            # The full-game cohort freezes its FIRST FINAL forecast. A paper
            # candidate may legitimately use a LATER FINAL injury update.
            if _dt(row["entry_at"]) < _dt(forecast["forecast_at"]):
                raise ValueError("paper selection predates the archived first FINAL forecast")
            if _dt(row["commence_time"]) != _dt(forecast["tipoff_at"]):
                raise ValueError("paper game tip-off mismatch")
            if _dt(row["entry_at"]) >= _dt(row["commence_time"]):
                raise ValueError("paper bet entered after tip-off")
            to_tip = (_dt(row["commence_time"]) - _dt(row["entry_at"])).total_seconds() / 60
            if not 5 <= to_tip <= 30:
                raise ValueError("paper entry outside FINAL 5-30 minute cohort")
            price = float(row["price"])
            if not math.isfinite(price) or price <= 1:
                raise ValueError("invalid paper price")
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"paper:{key}:{exc}")
    for key, row in c.items():
        try:
            original = p.get(key)
            if original is None:
                raise ValueError("closing record lacks original paper entry")
            if (row["game_id"] != original["game_id"]
                    or row["market"] != original["market"]
                    or row["selection"] != original["selection"]):
                raise ValueError("close and paper settlement contract differ")
            paper_event = str(original.get("odds_event_id") or "").strip()
            close_event = str(row.get("odds_event_id") or "").strip()
            if paper_event and close_event != paper_event:
                raise ValueError("close odds event id differs from paper entry")
            captured = _dt(row["captured_at"])
            if captured < _dt(original["entry_at"]) or captured >= _dt(original["commence_time"]):
                raise ValueError("close snapshot was not between entry and tip-off")
            probability = float(row["pinnacle_close_no_vig_probability"])
            if not math.isfinite(probability) or not 0 < probability < 1:
                raise ValueError("invalid closing no-vig probability")
            if row.get("price_clv_comparable") is True:
                if row["market"] != "ML":
                    if abs(float(row["entry_line"]) - float(row["close_line"])) > 1e-7:
                        raise ValueError("price CLV calculated on different lines")
                if row.get("clv_pp") is None:
                    raise ValueError("comparable close missing CLV")
            elif row.get("clv_pp") is not None:
                raise ValueError("noncomparable closing line carries price CLV")
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"close:{key}:{exc}")
    for key, row in s.items():
        try:
            original = p.get(key)
            if original is None:
                raise ValueError("settlement lacks paper entry")
            outcome = o.get(str(original["game_id"]))
            if outcome is None:
                raise ValueError("settlement lacks independently observed outcome")
            expected = settle_candidate(
                original, home_score=outcome["home_score"], away_score=outcome["away_score"])
            if (row.get("settlement") != expected["settlement"]
                    or abs(float(row["profit_bankroll_fraction"])
                           - float(expected["profit_bankroll_fraction"])) > 1e-9):
                raise ValueError("settlement or paper P/L does not match contract")
            if (int(row["home_score"]) != int(outcome["home_score"])
                    or int(row["away_score"]) != int(outcome["away_score"])):
                raise ValueError("settled score differs from official outcome")
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"settled:{key}:{exc}")
    for key, row in p.items():
        if key not in c and str(row.get("game_id") or "") in o:
            warnings.append(f"paper:{key}:closing_snapshot_missing")
        if key not in s and str(row.get("game_id") or "") in o:
            warnings.append(f"paper:{key}:settlement_missing")
    if not f:
        warnings.append("no_full_game_prospective_forecasts_yet")
    return {
        "schema": SCHEMA, "role": "RESEARCH_AUDIT_ONLY",
        "audited_at": now.isoformat(), "ok": not errors, "errors": errors,
        "warnings": warnings, "counts": {
            "final_forecasts": len(f), "official_outcomes": len(o),
            "paper_entries": len(p), "close_captures": len(c),
            "settled_entries": len(s),
        },
        "betting_certified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forecasts", default="runtime/evidence/final_forecasts.jsonl")
    parser.add_argument("--outcomes", default="runtime/evidence/final_outcomes.jsonl")
    parser.add_argument("--paper", default="runtime/evidence/paper_entries.jsonl")
    parser.add_argument("--close", default="runtime/evidence/close_ledger.jsonl")
    parser.add_argument("--settled", default="runtime/evidence/settled_paper.jsonl")
    parser.add_argument("--output", default="runtime/evidence/audit.json")
    args = parser.parse_args()
    report = audit_records(
        forecasts=_read(args.forecasts), outcomes=_read(args.outcomes),
        paper=_read(args.paper), closes=_read(args.close), settled=_read(args.settled))
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "counts": report["counts"],
                      "errors": report["errors"], "warnings": report["warnings"]}, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
