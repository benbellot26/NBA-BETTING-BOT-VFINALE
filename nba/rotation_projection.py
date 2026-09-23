from __future__ import annotations

import re
from typing import Any

from .rotations import RotationPlayer, validate_rotation


def _name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+","",str(value).lower())


def _num(row: dict[str,Any] | None, key: str, default: float=0.0) -> float:
    if not row: return default
    try: return float(row.get(key) or default)
    except Exception: return default


def project_rotation(
    team_id: int,
    *,
    season_base: list[dict[str,Any]],
    recent_base: list[dict[str,Any]],
    season_advanced: list[dict[str,Any]] | None=None,
    team_ortg: float=115.0,
    team_drtg: float=115.0,
    injury_status: dict[str,str] | None=None,
    max_players: int=12,
) -> list[RotationPlayer]:
    season={int(r["PLAYER_ID"]):r for r in season_base if int(r.get("TEAM_ID") or 0)==int(team_id) and r.get("PLAYER_ID") is not None}
    recent={int(r["PLAYER_ID"]):r for r in recent_base if int(r.get("TEAM_ID") or 0)==int(team_id) and r.get("PLAYER_ID") is not None}
    advanced={int(r["PLAYER_ID"]):r for r in (season_advanced or []) if int(r.get("TEAM_ID") or 0)==int(team_id) and r.get("PLAYER_ID") is not None}
    candidates=[]
    for pid,row in season.items():
        rec=recent.get(pid)
        season_min=_num(row,"MIN"); recent_min=_num(rec,"MIN",season_min)
        projected=.65*recent_min+.35*season_min
        if projected<=0: continue
        candidates.append((projected,pid,row))
    candidates=sorted(candidates,reverse=True)[:max_players]
    if not candidates: raise ValueError(f"no player minutes available for team_id={team_id}")
    raw_total=sum(x[0] for x in candidates)
    status_map={_name(k):str(v).upper() for k,v in (injury_status or {}).items()}
    rows=[]
    for raw,pid,base in candidates:
        minutes=240.0*raw/raw_total
        name=str(base.get("PLAYER_NAME") or pid)
        adv=advanced.get(pid) or {}
        off_delta=(_num(adv,"OFF_RATING",team_ortg)-team_ortg)*.15
        def_delta=(team_drtg-_num(adv,"DEF_RATING",team_drtg))*.15
        rows.append(RotationPlayer(
            player_id=str(pid), name=name, minutes=minutes,
            offensive_impact=max(-3.5,min(3.5,off_delta)),
            defensive_impact=max(-3.5,min(3.5,def_delta)),
            usage=_num(adv,"USG_PCT",_num(base,"USG_PCT",0.0)),
            status=status_map.get(_name(name),"AVAILABLE"),
        ))
    return validate_rotation(rows)
