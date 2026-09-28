from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from . import MODEL_GENERATION,PROBABILITY_POLICY_ID
from .paper_ledger import append_entry
from .portfolio_correlation import apply_correlation_cap
from .staking import size_portfolio

def _existing(path:Path)->set[str]:
    if not path.exists():return set()
    out=set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():continue
        try:out.add(str(json.loads(line).get("entry_key") or ""))
        except Exception:pass
    return out

def record_paper_candidates(live_run:dict[str,Any],path:str|Path)->dict[str,Any]:
    target=Path(path);seen=_existing(target);pending=[]
    for game in live_run.get("games") or []:
        if str(game.get("phase") or "").upper()!="FINAL":continue
        for c in (game.get("decision") or {}).get("candidates") or []:
            if c.get("paper_eligible") is not True:continue
            key=f"{game.get('game_id')}|{c.get('market')}|{c.get('selection')}"
            if key in seen:continue
            sized=dict(c);sized["status"]="BET";sized["game_id"]=game.get("game_id");sized["_entry_key"]=key;sized["_game"]=game;pending.append(sized)
    sized=apply_correlation_cap(size_portfolio(pending,certified=True))
    added=0
    for c in sized:
        game=c.pop("_game");key=c.pop("_entry_key")
        row={"entry_key":key,"entry_type":"RESEARCH_PAPER_CANDIDATE","model_generation":MODEL_GENERATION,"probability_policy_id":PROBABILITY_POLICY_ID,"game_id":game.get("game_id"),"odds_event_id":game.get("odds_event_id"),"game_date":game.get("game_date"),"commence_time":game.get("commence_time"),"home":game.get("home"),"away":game.get("away"),"phase":game.get("phase"),"market":c.get("market"),"selection":c.get("selection"),"price":c.get("price"),"line":c.get("line"),"model_probability":c.get("model_probability"),"lower_probability":c.get("lower_probability"),"sharp_probability_entry":c.get("sharp_probability"),"execution_book":c.get("execution_book"),"stake_fraction":c.get("stake_fraction"),"entry_at":game.get("analyzed_at"),"source_snapshot_sha256":game.get("source_snapshot_sha256"),"source_snapshot_at":game.get("source_snapshot_at"),"input_manifest":game.get("input_manifest"),"status":"PAPER"}
        append_entry(target,row);seen.add(key);added+=1
    return {"added":added,"total_keys":len(seen)}

from .tracking import append_jsonl


def _sharp_probability(game: dict[str, Any], selection: str) -> float | None:
    for candidate in (game.get("decision") or {}).get("candidates") or []:
        if candidate.get("selection") == selection and candidate.get("sharp_probability") is not None:
            return float(candidate["sharp_probability"])
    return None


def record_final_forecasts(live_run: dict[str, Any], path: str | Path) -> dict[str, int]:
    """Store one genuinely pre-tip FINAL prediction for every analyzable game.

    Unlike the paper ledger, this cohort is NOT selected by bet edge.
    It is used to evaluate overall forecast calibration without selection bias.
    """
    target = Path(path)
    existing = _existing(target)
    added = 0
    for game in live_run.get("games") or []:
        if game.get("phase") != "FINAL":
            continue
        if not (game.get("input_quality") or {}).get("eligible"):
            continue
        identity = str(game.get("model_generation") or "")
        key = f"{game.get('game_id')}|{identity}|FINAL"
        if key in existing:
            continue
        snapshot = str(game.get("source_snapshot_sha256") or "")
        if len(snapshot) != 64:
            continue
        score = game["score_projection"]
        probabilities = game.get("probabilities") or {}
        sharp = {
            "ML": _sharp_probability(game, "home_ml"),
            "SPREAD": _sharp_probability(game, "home_spread"),
            "TOTAL": _sharp_probability(game, "over"),
        }
        sharp = {key: value for key, value in sharp.items() if value is not None}
        consensus_markets = (
            (game.get("market_benchmark") or {}).get("markets") or {}
        )
        consensus = {}
        consensus_metadata = {}
        for market_name, selection_name in (
            ("ML", "HOME"), ("SPREAD", "HOME"), ("TOTAL", "OVER")
        ):
            row = consensus_markets.get(market_name) or {}
            if row.get(selection_name) is None:
                continue
            consensus[market_name] = float(row[selection_name])
            consensus_metadata[market_name] = {
                "book_count": int(row.get("book_count") or 0),
                "dispersion_pp": row.get("dispersion_pp"),
                "point": row.get("point"),
                "pinnacle_included": row.get("pinnacle_included") is True,
                "role": row.get("role"),
            }
        evaluation_only = {
            "spread_line": probabilities.get("spread_line"),
            "total_line": probabilities.get("total_line"),
            "pinnacle_entry_probability": sharp,
            "consensus_entry_probability": consensus,
            "consensus_metadata": consensus_metadata,
        }
        record = {
            "entry_key": key, "game_id": game["game_id"],
            "game_date": game["game_date"],
            "home": game.get("home"), "away": game.get("away"),
            "model_generation": identity,
            "source_snapshot_sha256": snapshot,
            "source_snapshot_at": game["source_snapshot_at"],
            "forecast_at": game["analyzed_at"],
            "tipoff_at": game["commence_time"],
            "baseline_margin": score["margin_mean"],
            "baseline_total": score["total_mean"],
            "baseline_margin_sd": score["margin_sd"],
            "baseline_total_sd": score["total_sd"],
            "role": "PIT_FINAL_FORECAST",
            "probabilities": game.get("probabilities"),
            "input_manifest": game.get("input_manifest"),
            "v2_features": game.get("v2_features"),
            # Market-derived information is retained only for scoring. Learned
            # V2 feature validation never exposes this object to training.
            "evaluation_only": evaluation_only,
        }
        append_jsonl(target, record)
        existing.add(key)
        added += 1
    return {"added": added, "total_keys": len(existing)}
