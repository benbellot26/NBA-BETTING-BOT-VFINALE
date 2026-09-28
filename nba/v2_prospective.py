"""Score immutable prospective learned-V2 shadow forecasts after official outcomes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

from . import MODEL_GENERATION
from .performance import brier, calibration_ece, logloss, mae
from .v2_model import LEARNED_GENERATION

TRUSTED_OUTCOME_SOURCES = {"official_nba_schedule", "official_nba_gamebook"}


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("V2 prospective timestamps require timezone")
    return parsed.astimezone(timezone.utc)


def _read(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    return [
        json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _p(value: Any, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be numeric") from None
    if not math.isfinite(parsed) or not 0.0 <= parsed <= 1.0:
        raise ValueError(f"{name} must be a probability")
    return parsed


def _proper(rows: list[tuple[float, int]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0, "brier": None, "logloss": None, "ece": None}
    return {
        "n": len(rows),
        "brier": sum(brier(p, y) for p, y in rows) / len(rows),
        "logloss": sum(logloss(p, y) for p, y in rows) / len(rows),
        "ece": calibration_ece(rows),
    }


def evaluate(
    *,
    forecasts_path: str = "runtime/research/v2_live_forecasts.jsonl",
    outcomes_path: str = "runtime/evidence/final_outcomes.jsonl",
    output_path: str = "runtime/research/v2_prospective_performance.json",
) -> dict[str, Any]:
    forecasts = _read(forecasts_path)
    outcomes = _read(outcomes_path)
    observed = {str(row.get("game_id")): row for row in outcomes}
    if len(observed) != len(outcomes):
        raise ValueError("duplicate official outcomes in V2 prospective evaluation")

    champion_ml: list[tuple[float, int]] = []
    shadow_ml: list[tuple[float, int]] = []
    champion_spread: list[tuple[float, int]] = []
    shadow_spread: list[tuple[float, int]] = []
    champion_total: list[tuple[float, int]] = []
    shadow_total: list[tuple[float, int]] = []
    pinnacle: dict[str, list[tuple[float, int]]] = {
        "ML": [], "SPREAD": [], "TOTAL": [],
    }
    champion_margin, shadow_margin, actual_margin = [], [], []
    champion_totals, shadow_totals, actual_totals = [], [], []
    resolved_ids: list[str] = []

    seen: set[str] = set()
    for forecast in forecasts:
        key = str(forecast.get("entry_key") or "")
        if not key or key in seen:
            raise ValueError("duplicate or missing V2 prospective entry key")
        seen.add(key)
        if forecast.get("role") != "SHADOW_PIT_FORECAST":
            raise ValueError("non-shadow record in V2 prospective ledger")
        if forecast.get("champion_generation") != MODEL_GENERATION:
            raise ValueError("V2 prospective champion generation mismatch")
        if forecast.get("shadow_generation") != LEARNED_GENERATION:
            raise ValueError("V2 prospective shadow generation mismatch")
        if forecast.get("promoted") is not False or forecast.get("betting_certified") is not False:
            raise ValueError("V2 prospective ledger contains forbidden promotion state")
        if forecast.get("market_data_used_as_feature") is not False:
            raise ValueError("V2 prospective record permits market feature leakage")
        game_id = str(forecast.get("game_id") or "")
        outcome = observed.get(game_id)
        if outcome is None:
            continue
        if outcome.get("source") not in TRUSTED_OUTCOME_SOURCES:
            raise ValueError("V2 prospective outcome is not from a trusted official NBA source")
        forecast_at = _dt(str(forecast["forecast_at"]))
        tipoff_at = _dt(str(forecast["tipoff_at"]))
        outcome_at = _dt(str(outcome["outcome_at"]))
        trained_through = _dt(str(forecast["trained_through"]))
        if not (trained_through <= forecast_at < tipoff_at < outcome_at):
            raise ValueError("V2 prospective chronology violation")

        home = float(outcome["home_score"])
        away = float(outcome["away_score"])
        margin = home - away
        total_points = home + away
        champion = forecast.get("champion") or {}
        shadow = forecast.get("prediction") or {}
        evaluation = forecast.get("evaluation_only") or {}
        sharp = evaluation.get("pinnacle_entry_probability") or {}
        spread_line = float(evaluation["spread_line"])
        total_line = float(evaluation["total_line"])

        champion_ml.append((_p(champion["home_ml"], "champion.home_ml"), int(margin > 0)))
        shadow_ml.append((_p(shadow["home_ml"], "shadow.home_ml"), int(margin > 0)))
        champion_margin.append(float(champion["margin_mean"]))
        shadow_margin.append(float(shadow["margin_mean"]))
        actual_margin.append(margin)
        champion_totals.append(float(champion["total_mean"]))
        shadow_totals.append(float(shadow["total_mean"]))
        actual_totals.append(total_points)

        spread_delta = margin + spread_line
        if spread_delta != 0:
            label = int(spread_delta > 0)
            champion_spread.append((_p(champion["home_spread"], "champion.home_spread"), label))
            shadow_spread.append((_p(shadow["home_spread"], "shadow.home_spread"), label))
            if sharp.get("SPREAD") is not None:
                pinnacle["SPREAD"].append((_p(sharp["SPREAD"], "pinnacle.SPREAD"), label))

        total_delta = total_points - total_line
        if total_delta != 0:
            label = int(total_delta > 0)
            champion_total.append((_p(champion["over"], "champion.over"), label))
            shadow_total.append((_p(shadow["over"], "shadow.over"), label))
            if sharp.get("TOTAL") is not None:
                pinnacle["TOTAL"].append((_p(sharp["TOTAL"], "pinnacle.TOTAL"), label))

        if sharp.get("ML") is not None:
            pinnacle["ML"].append((_p(sharp["ML"], "pinnacle.ML"), int(margin > 0)))
        resolved_ids.append(game_id)

    if not resolved_ids:
        report = {
            "schema": "pulsar-nba-v2-prospective-v1",
            "role": "SHADOW",
            "status": "NO_RESOLVED_FORECASTS",
            "promoted": False,
            "auto_betting_certification": False,
            "market_data_used_as_feature": False,
            "holdout_champion": {"n": 0},
            "holdout_shadow": {"n": 0},
            "holdout_pinnacle_entry": {"ml_n": 0, "spread_n": 0, "total_n": 0},
            "resolved_game_ids": [],
        }
    else:
        champ_ml = _proper(champion_ml)
        shad_ml = _proper(shadow_ml)
        champ_sp = _proper(champion_spread)
        shad_sp = _proper(shadow_spread)
        champ_tot = _proper(champion_total)
        shad_tot = _proper(shadow_total)
        champion_metrics = {
            "n": len(resolved_ids),
            "ml_brier": champ_ml["brier"],
            "ml_logloss": champ_ml["logloss"],
            "ml_ece": champ_ml["ece"],
            "margin_mae": mae(champion_margin, actual_margin),
            "total_mae": mae(champion_totals, actual_totals),
            "spread_n": champ_sp["n"],
            "spread_brier": champ_sp["brier"],
            "spread_logloss": champ_sp["logloss"],
            "spread_ece": champ_sp["ece"],
            "total_n": champ_tot["n"],
            "total_brier": champ_tot["brier"],
            "total_logloss": champ_tot["logloss"],
            "total_ece": champ_tot["ece"],
        }
        shadow_metrics = {
            "n": len(resolved_ids),
            "ml_brier": shad_ml["brier"],
            "ml_logloss": shad_ml["logloss"],
            "ml_ece": shad_ml["ece"],
            "margin_mae": mae(shadow_margin, actual_margin),
            "total_mae": mae(shadow_totals, actual_totals),
            "spread_n": shad_sp["n"],
            "spread_brier": shad_sp["brier"],
            "spread_logloss": shad_sp["logloss"],
            "spread_ece": shad_sp["ece"],
            "total_n": shad_tot["n"],
            "total_brier": shad_tot["brier"],
            "total_logloss": shad_tot["logloss"],
            "total_ece": shad_tot["ece"],
        }
        pin_metrics: dict[str, Any] = {}
        for market, pairs in pinnacle.items():
            scored = _proper(pairs)
            prefix = market.lower()
            pin_metrics[f"{prefix}_n"] = scored["n"]
            pin_metrics[f"{prefix}_brier"] = scored["brier"]
            pin_metrics[f"{prefix}_logloss"] = scored["logloss"]
            pin_metrics[f"{prefix}_ece"] = scored["ece"]
        report = {
            "schema": "pulsar-nba-v2-prospective-v1",
            "role": "SHADOW",
            "status": "PROSPECTIVE_EVIDENCE",
            "promoted": False,
            "auto_betting_certification": False,
            "market_data_used_as_feature": False,
            "holdout_champion": champion_metrics,
            "holdout_shadow": shadow_metrics,
            "holdout_pinnacle_entry": pin_metrics,
            "resolved_game_ids": resolved_ids,
        }

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Score prospective frozen V2 shadow forecasts")
    parser.add_argument("--forecasts", default="runtime/research/v2_live_forecasts.jsonl")
    parser.add_argument("--outcomes", default="runtime/evidence/final_outcomes.jsonl")
    parser.add_argument("--output", default="runtime/research/v2_prospective_performance.json")
    args = parser.parse_args()
    report = evaluate(
        forecasts_path=args.forecasts,
        outcomes_path=args.outcomes,
        output_path=args.output,
    )
    print(json.dumps({
        "status": report["status"],
        "resolved": report["holdout_shadow"]["n"],
        "promoted": False,
    }, indent=2))


if __name__ == "__main__":
    main()
