from __future__ import annotations
from dataclasses import asdict
from typing import Any,Iterable
from .decision import evaluate_candidate
from .distribution import probability_surface
from .market import best_execution,pinnacle_no_vig
from .model import GameContext,TeamMetrics,prediction_payload
from .rotations import RotationPlayer
from .structural import project_game
from .uncertainty import intervals

def analyze_game(*,home:TeamMetrics,away:TeamMetrics,context:GameContext,spread_line:float,total_line:float,books_by_market:dict[str,list[dict[str,Any]]]|None=None,certification:dict[str,Any]|None=None,home_rotation:Iterable[RotationPlayer]|None=None,away_rotation:Iterable[RotationPlayer]|None=None,market_fresh:bool=True,betting_window_ok:bool=False)->dict[str,Any]:
    projection,components=project_game(home=home,away=away,context=context,home_rotation=home_rotation,away_rotation=away_rotation)
    surface=probability_surface(projection,spread_line=spread_line,total_line=total_line); payload=prediction_payload(projection,surface,components=components); probs=asdict(surface)
    unresolved=projection.data_quality=="LINEUP_UNCERTAIN"; bands=intervals(probs,data_quality=projection.data_quality,market_fresh=market_fresh,unresolved_key_player=unresolved)
    payload["probability_intervals"]=bands; payload["decision"]={"candidates":[]}
    if not books_by_market:return payload
    cert=certification or {"certified":False,"markets":{}}
    specs=[("home_ml","ML","HOME","AWAY",None),("away_ml","ML","AWAY","HOME",None),("home_spread","SPREAD","HOME","AWAY",spread_line),("away_spread","SPREAD","AWAY","HOME",-spread_line),("over","TOTAL","OVER","UNDER",total_line),("under","TOTAL","UNDER","OVER",total_line)]
    for key,market,left,right,point in specs:
        books=books_by_market.get(market) or []; execution=best_execution(books,left,point=point)
        if not execution:continue
        sharp=pinnacle_no_vig(books,left,right,point=point); sharp_p=None if not sharp else sharp.get(left)
        mcert=((cert.get("markets") or {}).get(market) or {}).get("betting_certified") is True and cert.get("certified") is True
        candidate=evaluate_candidate(selection=key,market=market,model_probability=float(probs[key]),lower_probability=float(bands["selections"][key]["lower"]),price=float(execution["price"]),sharp_probability=sharp_p,certified=mcert,market_fresh=market_fresh,lineup_unresolved=unresolved,timing_eligible=betting_window_ok)
        candidate["execution_book"]=execution.get("bookmaker");candidate["game_id"]=context.game_id;candidate["line"]=point;payload["decision"]["candidates"].append(candidate)
    return payload
