"""Join immutable paper and all-game evidence without selection-biased calibration."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

from .certification import certify
from .evidence_audit import audit_records
from .model import ProbabilitySurface
from .performance import brier, calibration_ece, logloss
from .providers import OfficialOutcomeProvider
from .schedule import fetch_schedule
from .settlement import settle_candidate
from .teams import canonical_team
from .tracking import append_jsonl


def _read(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _write(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _proper_scores(pairs: list[tuple[float, int]]) -> dict[str, Any]:
    if not pairs:
        return {"n": 0, "brier": None, "logloss": None, "ece": None}
    return {
        "n": len(pairs),
        "brier": sum(brier(p, y) for p, y in pairs) / len(pairs),
        "logloss": sum(logloss(p, y) for p, y in pairs) / len(pairs),
        "ece": calibration_ece(pairs),
    }


def full_game_cohorts(
    forecasts: list[dict[str, Any]], outcomes: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """One canonical selection for each market and game, never bet-selected.

    HOME ML, HOME spread and OVER total avoid double counting complements.
    A whole-number spread/total push has no binary label and is excluded
    from that market's resolved observations.
    """
    observed = {str(row["game_id"]): row for row in outcomes}
    pairs: dict[str, list[tuple[float, int]]] = {
        "ML": [], "SPREAD": [], "TOTAL": [],
    }
    for forecast in forecasts:
        result = observed.get(str(forecast.get("game_id")))
        probabilities = forecast.get("probabilities")
        if result is None or probabilities is None:
            continue
        surface = ProbabilitySurface(**probabilities).validated()
        home = float(result["home_score"])
        away = float(result["away_score"])
        if home != away:
            pairs["ML"].append((surface.home_ml, int(home > away)))
        cover_delta = home - away + surface.spread_line
        total_delta = home + away - surface.total_line
        if cover_delta != 0:
            pairs["SPREAD"].append((surface.home_spread, int(cover_delta > 0)))
        if total_delta != 0:
            pairs["TOTAL"].append((surface.over, int(total_delta > 0)))
    return {
        market: {
            "full_cohort_n": scores["n"],
            "full_cohort_brier": scores["brier"],
            "full_cohort_logloss": scores["logloss"],
            "full_cohort_ece": scores["ece"],
        }
        for market, scores in (
            (key, _proper_scores(value)) for key, value in pairs.items()
        )
    }


def consensus_benchmark_cohorts(
    forecasts: list[dict[str, Any]], outcomes: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Score market consensus only on games where that benchmark was captured.

    This evidence is research-only and is not consumed by certification.
    Model and consensus probabilities are paired on the exact same contracts.
    """
    observed = {str(row["game_id"]): row for row in outcomes}
    benchmark_pairs: dict[str, list[tuple[float, int]]] = {
        "ML": [], "SPREAD": [], "TOTAL": [],
    }
    model_pairs: dict[str, list[tuple[float, int]]] = {
        "ML": [], "SPREAD": [], "TOTAL": [],
    }
    book_counts: dict[str, list[int]] = {
        "ML": [], "SPREAD": [], "TOTAL": [],
    }
    dispersions: dict[str, list[float]] = {
        "ML": [], "SPREAD": [], "TOTAL": [],
    }
    for forecast in forecasts:
        result = observed.get(str(forecast.get("game_id")))
        probabilities = forecast.get("probabilities")
        evaluation = forecast.get("evaluation_only") or {}
        consensus = evaluation.get("consensus_entry_probability") or {}
        metadata = evaluation.get("consensus_metadata") or {}
        if result is None or probabilities is None:
            continue
        surface = ProbabilitySurface(**probabilities).validated()
        home = float(result["home_score"])
        away = float(result["away_score"])
        labels: dict[str, int | None] = {
            "ML": int(home > away) if home != away else None,
            "SPREAD": None,
            "TOTAL": None,
        }
        cover_delta = home - away + surface.spread_line
        total_delta = home + away - surface.total_line
        if cover_delta != 0:
            labels["SPREAD"] = int(cover_delta > 0)
        if total_delta != 0:
            labels["TOTAL"] = int(total_delta > 0)
        model_probability = {
            "ML": surface.home_ml,
            "SPREAD": surface.home_spread,
            "TOTAL": surface.over,
        }
        for market in ("ML", "SPREAD", "TOTAL"):
            if labels[market] is None or consensus.get(market) is None:
                continue
            value = float(consensus[market])
            if not 0.0 <= value <= 1.0:
                raise ValueError("consensus probability outside [0,1]")
            meta = metadata.get(market) or {}
            if meta.get("pinnacle_included") is True:
                raise ValueError("evaluation consensus unexpectedly includes Pinnacle")
            count = int(meta.get("book_count") or 0)
            if count < 3:
                raise ValueError("evaluation consensus has fewer than three books")
            benchmark_pairs[market].append((value, int(labels[market])))
            model_pairs[market].append(
                (float(model_probability[market]), int(labels[market]))
            )
            book_counts[market].append(count)
            if meta.get("dispersion_pp") is not None:
                dispersions[market].append(float(meta["dispersion_pp"]))

    result: dict[str, dict[str, Any]] = {}
    for market in ("ML", "SPREAD", "TOTAL"):
        benchmark = _proper_scores(benchmark_pairs[market])
        model = _proper_scores(model_pairs[market])
        result[market] = {
            "n": benchmark["n"],
            "consensus_brier": benchmark["brier"],
            "consensus_logloss": benchmark["logloss"],
            "consensus_ece": benchmark["ece"],
            "model_brier_paired": model["brier"],
            "model_logloss_paired": model["logloss"],
            "model_ece_paired": model["ece"],
            "mean_book_count": (
                sum(book_counts[market]) / len(book_counts[market])
                if book_counts[market] else None
            ),
            "mean_dispersion_pp": (
                sum(dispersions[market]) / len(dispersions[market])
                if dispersions[market] else None
            ),
            "role": "EVALUATION_ONLY",
            "used_for_certification": False,
        }
    return result


def _final_for_record(
    record: dict[str, Any], finals: dict[str, Any],
):
    """Resolve an official final without inventing a missing NBA GameID.

    Exact GameID is always preferred. The date/team fallback is permitted only
    for explicit nba-pr-* identities created from the official Communications
    pregame PDF, and only when it resolves to exactly one official final.
    """
    game_id = str(record.get("game_id") or "")
    exact = finals.get(game_id)
    if exact is not None:
        return exact
    if not game_id.startswith("nba-pr-"):
        return None
    home = str(record.get("home") or "")
    away = str(record.get("away") or "")
    game_date = str(record.get("game_date") or "")
    if not home or not away or not game_date:
        return None
    matching = [
        game for game in finals.values()
        if game.game_date == game_date
        and canonical_team(game.home) == canonical_team(home)
        and canonical_team(game.away) == canonical_team(away)
    ]
    if len(matching) > 1:
        raise ValueError(
            f"ambiguous official final for Communications identity {game_id}"
        )
    return matching[0] if matching else None


def _merge_close(row: dict[str, Any], close: dict[str, Any] | None) -> dict[str, Any]:
    """Late historical closes update a derived view, not the settled JSONL."""
    result = dict(row)
    if close is not None:
        result.update({
            "close_no_vig_probability": close.get("pinnacle_close_no_vig_probability"),
            "clv_pp": close.get("clv_pp"),
            "line_clv": close.get("line_clv"),
            "price_clv_comparable": close.get("price_clv_comparable"),
        })
    return result


def refresh(
    *, paper_path: str, close_path: str, settled_path: str,
    performance_path: str, certification_path: str,
    forecasts_path: str = "runtime/evidence/final_forecasts.jsonl",
    outcomes_path: str = "runtime/evidence/final_outcomes.jsonl",
    audit_path: str = "runtime/evidence/audit.json",
    outcome_provider: OfficialOutcomeProvider | None = None,
) -> dict[str, Any]:
    paper = _read(paper_path)
    closes = _read(close_path)
    closing = {str(row["entry_key"]): row for row in closes}
    existing_settlements = _read(settled_path)
    settled = {str(row["entry_key"]): row for row in existing_settlements}
    forecasts = _read(forecasts_path)
    outcomes = _read(outcomes_path)
    known = {str(row.get("game_id")) for row in outcomes}
    finals = (outcome_provider or OfficialOutcomeProvider(fetcher=fetch_schedule)).finals()
    for forecast in forecasts:
        game_id = str(forecast.get("game_id") or "")
        if game_id in known:
            continue
        game = _final_for_record(forecast, finals)
        if game is None:
            continue
        observed = {
            "game_id": game_id,
            "official_game_id": game.game_id,
            "home_score": game.home_score,
            "away_score": game.away_score,
            "outcome_at": datetime.now(timezone.utc).isoformat(),
            "source": "official_nba_schedule",
        }
        append_jsonl(outcomes_path, observed)
        outcomes.append(observed)
        known.add(game_id)
    for entry in paper:
        key = str(entry["entry_key"])
        if key in settled:
            continue
        game = _final_for_record(entry, finals)
        if game is None:
            continue
        settled_row = settle_candidate(
            entry, home_score=game.home_score, away_score=game.away_score)
        settled_row["entry_key"] = key
        settled_row = _merge_close(settled_row, closing.get(key))
        append_jsonl(settled_path, settled_row)
        settled[key] = settled_row
        existing_settlements.append(settled_row)
    audit = audit_records(
        forecasts=forecasts, outcomes=outcomes, paper=paper,
        closes=closes, settled=existing_settlements,
    )
    _write(audit_path, audit)
    merged = [_merge_close(row, closing.get(key)) for key, row in settled.items()]
    full = full_game_cohorts(forecasts, outcomes) if audit["ok"] else {
        market: {
            "full_cohort_n": 0, "full_cohort_brier": None,
            "full_cohort_logloss": None, "full_cohort_ece": None,
        } for market in ("ML", "SPREAD", "TOTAL")
    }
    markets: dict[str, dict[str, Any]] = {}
    for market in ("ML", "SPREAD", "TOTAL"):
        cohort = [
            row for row in merged if row.get("market") == market
            and row.get("settlement") in {"WIN", "LOSS"}
        ]
        scores = _proper_scores([
            (float(row["model_probability"]), int(row["settlement"] == "WIN"))
            for row in cohort
        ])
        paired = [
            row for row in cohort
            if row.get("price_clv_comparable") is True
            and row.get("close_no_vig_probability") is not None
        ]
        clv = [
            float(row["clv_pp"]) for row in paired
            if row.get("clv_pp") is not None and math.isfinite(float(row["clv_pp"]))
        ]
        markets[market] = {
            **scores, **full[market],
            "paired_sharp_n": len(paired),
            "model_brier_paired": (
                sum(brier(float(row["model_probability"]),
                          int(row["settlement"] == "WIN")) for row in paired) / len(paired)
                if paired else None),
            "sharp_brier_paired": (
                sum(brier(float(row["close_no_vig_probability"]),
                          int(row["settlement"] == "WIN")) for row in paired) / len(paired)
                if paired else None),
            "clv_n": len(clv),
            "mean_clv_pp": sum(clv) / len(clv) if clv else None,
            "positive_clv_rate": sum(value > 0 for value in clv) / len(clv) if clv else None,
        }
    consensus_benchmark = (
        consensus_benchmark_cohorts(forecasts, outcomes)
        if audit["ok"] else {
            market: {
                "n": 0, "consensus_brier": None, "consensus_logloss": None,
                "consensus_ece": None, "model_brier_paired": None,
                "model_logloss_paired": None, "model_ece_paired": None,
                "mean_book_count": None, "mean_dispersion_pp": None,
                "role": "EVALUATION_ONLY", "used_for_certification": False,
            }
            for market in ("ML", "SPREAD", "TOTAL")
        }
    )
    completed = {str(row["game_id"]) for row in forecasts} & known
    evidence = {
        "schema": "pulsar-nba-performance-v2", "games": len(completed),
        "settled_entries": len(existing_settlements),
        "audit_ok": audit["ok"], "audit_errors": audit["errors"],
        "calibration_cohort": "FIRST_FINAL_ALL_ANALYZABLE_GAMES",
        "paper_cohort": "FIRST_QUALIFYING_SELECTION_PER_GAME",
        "markets": markets,
        "market_benchmarks": {
            "consensus": {
                "role": "EVALUATION_ONLY",
                "used_for_certification": False,
                "pinnacle_replacement": False,
                "markets": consensus_benchmark,
            }
        },
    }
    candidate = certify(evidence)
    candidate["evidence"] = evidence
    _write(performance_path, evidence)
    _write(certification_path, candidate)
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", default="runtime/evidence/paper_entries.jsonl")
    parser.add_argument("--close", default="runtime/evidence/close_ledger.jsonl")
    parser.add_argument("--settled", default="runtime/evidence/settled_paper.jsonl")
    parser.add_argument("--performance", default="runtime/evidence/performance.json")
    parser.add_argument("--certification", default="runtime/evidence/certification_candidate.json")
    parser.add_argument("--forecasts", default="runtime/evidence/final_forecasts.jsonl")
    parser.add_argument("--outcomes", default="runtime/evidence/final_outcomes.jsonl")
    parser.add_argument("--audit", default="runtime/evidence/audit.json")
    args = parser.parse_args()
    result = refresh(
        paper_path=args.paper, close_path=args.close, settled_path=args.settled,
        performance_path=args.performance, certification_path=args.certification,
        forecasts_path=args.forecasts, outcomes_path=args.outcomes,
        audit_path=args.audit,
    )
    print(json.dumps({
        "certified": result["certified"],
        "audit_ok": result["evidence"]["audit_ok"],
        "games": result["evidence"]["games"],
        "failures": result["failures"],
    }, indent=2))


if __name__ == "__main__":
    main()
