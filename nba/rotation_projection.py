from __future__ import annotations

import re
import unicodedata
from typing import Any
from .rotations import RotationPlayer, validate_rotation


def normalized_player_name(value: str) -> str:
    plain = unicodedata.normalize("NFKD", str(value))
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", plain.casefold())


def _num(row: dict[str, Any] | None, key: str, default: float = 0.0) -> float:
    if row is None:
        return default
    try:
        value = row.get(key)
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def project_rotation(
    team_id: int, *, season_base: list[dict[str, Any]], recent_base: list[dict[str, Any]],
    season_advanced: list[dict[str, Any]] | None = None,
    team_ortg: float = 115.0, team_drtg: float = 115.0,
    injury_status: dict[str, str] | None = None, max_players: int = 12,
) -> list[RotationPlayer]:
    season = {int(r["PLAYER_ID"]): r for r in season_base
              if int(r.get("TEAM_ID") or 0) == int(team_id) and r.get("PLAYER_ID") is not None}
    recent = {int(r["PLAYER_ID"]): r for r in recent_base
              if int(r.get("TEAM_ID") or 0) == int(team_id) and r.get("PLAYER_ID") is not None}
    advanced = {int(r["PLAYER_ID"]): r for r in (season_advanced or [])
                if int(r.get("TEAM_ID") or 0) == int(team_id) and r.get("PLAYER_ID") is not None}
    candidates = []
    for pid, row in season.items():
        current = recent.get(pid)
        season_min = _num(row, "MIN")
        recent_min = _num(current, "MIN", season_min)
        projected = .65 * recent_min + .35 * season_min
        if projected > 0:
            candidates.append((projected, pid, row))
    candidates.sort(reverse=True)
    candidates = candidates[:max_players]
    if len(candidates) < 6:
        raise ValueError("insufficient rotation coverage")
    total = sum(item[0] for item in candidates)
    injuries = {normalized_player_name(name): str(status).upper()
                for name, status in (injury_status or {}).items()}
    rows = []
    for projected, pid, base in candidates:
        name = str(base.get("PLAYER_NAME") or pid)
        stats = advanced.get(pid) or {}
        off_delta = (_num(stats, "OFF_RATING", team_ortg) - team_ortg) * .15
        def_delta = (team_drtg - _num(stats, "DEF_RATING", team_drtg)) * .15
        rows.append(RotationPlayer(
            player_id=str(pid), name=name, minutes=240.0 * projected / total,
            offensive_impact=max(-3.5, min(3.5, off_delta)),
            defensive_impact=max(-3.5, min(3.5, def_delta)),
            usage=_num(stats, "USG_PCT", _num(base, "USG_PCT")),
            status=injuries.get(normalized_player_name(name), "AVAILABLE"),
        ))
    return validate_rotation(rows)
