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
        row={"entry_key":key,"entry_type":"RESEARCH_PAPER_CANDIDATE","model_generation":MODEL_GENERATION,"probability_policy_id":PROBABILITY_POLICY_ID,"game_id":game.get("game_id"),"game_date":game.get("game_date"),"commence_time":game.get("commence_time"),"home":game.get("home"),"away":game.get("away"),"phase":game.get("phase"),"market":c.get("market"),"selection":c.get("selection"),"price":c.get("price"),"line":c.get("line"),"model_probability":c.get("model_probability"),"lower_probability":c.get("lower_probability"),"sharp_probability_entry":c.get("sharp_probability"),"execution_book":c.get("execution_book"),"stake_fraction":c.get("stake_fraction"),"entry_at":game.get("analyzed_at"),"status":"PAPER"}
        append_entry(target,row);seen.add(key);added+=1
    return {"added":added,"total_keys":len(seen)}
