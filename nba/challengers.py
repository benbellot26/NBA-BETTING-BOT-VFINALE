from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from .model import ScoreProjection

CHALLENGERS=("pace","player_impact","injury_uncertainty","rest","travel","rotation","matchup","three_point_variance","rebounding","referee","garbage_time","distribution")


def shadow_variants(projection: ScoreProjection, *, external: dict[str,float] | None=None) -> dict[str,dict[str,Any]]:
    """Research-only counterfactuals. None can authorize a wager."""
    p=projection.validated(); ext=external or {}; out={}
    def add(name: str, row: ScoreProjection, note: str): out[name]={"role":"SHADOW","projection":asdict(row),"note":note}
    add("pace", replace(p,home_points=p.home_points*1.01,away_points=p.away_points*1.01,total_mean=p.total_mean*1.01,margin_mean=(p.home_points-p.away_points)*1.01), "1% pace stress")
    add("player_impact", replace(p,margin_mean=p.margin_mean+float(ext.get("player_margin_delta",0.0)),home_points=p.home_points+float(ext.get("player_margin_delta",0.0))/2,away_points=p.away_points-float(ext.get("player_margin_delta",0.0))/2), "external PIT player-impact residual")
    add("injury_uncertainty", replace(p,margin_sd=p.margin_sd*1.10,total_sd=p.total_sd*1.08), "wider injury uncertainty")
    add("rest", replace(p,margin_mean=p.margin_mean+float(ext.get("rest_margin_delta",0.0)),home_points=p.home_points+float(ext.get("rest_margin_delta",0.0))/2,away_points=p.away_points-float(ext.get("rest_margin_delta",0.0))/2), "rest residual")
    add("travel", replace(p,margin_mean=p.margin_mean+float(ext.get("travel_margin_delta",0.0)),home_points=p.home_points+float(ext.get("travel_margin_delta",0.0))/2,away_points=p.away_points-float(ext.get("travel_margin_delta",0.0))/2), "travel residual")
    add("rotation", replace(p,margin_sd=p.margin_sd*1.05), "rotation-risk stress")
    add("matchup", replace(p,margin_mean=p.margin_mean*1.05,home_points=p.total_mean/2+p.margin_mean*1.05/2,away_points=p.total_mean/2-p.margin_mean*1.05/2), "matchup residual stress")
    add("three_point_variance", replace(p,margin_sd=p.margin_sd*1.12,total_sd=p.total_sd*1.12), "3P variance stress")
    add("rebounding", replace(p,total_mean=p.total_mean+float(ext.get("rebound_total_delta",0.0)),home_points=p.home_points+float(ext.get("rebound_total_delta",0.0))/2,away_points=p.away_points+float(ext.get("rebound_total_delta",0.0))/2), "rebounding residual")
    add("referee", replace(p,total_mean=p.total_mean+float(ext.get("referee_total_delta",0.0)),home_points=p.home_points+float(ext.get("referee_total_delta",0.0))/2,away_points=p.away_points+float(ext.get("referee_total_delta",0.0))/2), "officiating residual; shadow only")
    add("garbage_time", replace(p,total_sd=p.total_sd*(1.08 if abs(p.margin_mean)>=10 else 1.0)), "garbage-time variance stress")
    add("distribution", replace(p,margin_sd=p.margin_sd*1.15,total_sd=p.total_sd*1.15), "heavy-tail proxy stress")
    return out
