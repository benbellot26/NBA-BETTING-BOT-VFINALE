from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RotationPlayer:
    player_id: str
    name: str
    minutes: float
    offensive_impact: float = 0.0
    defensive_impact: float = 0.0
    usage: float = 0.0
    status: str = "AVAILABLE"


def validate_rotation(players: Iterable[RotationPlayer], *, tolerance: float = .75) -> list[RotationPlayer]:
    rows = list(players)
    if not rows:
        raise ValueError("rotation cannot be empty")
    total = sum(max(0.0, p.minutes) for p in rows)
    if abs(total - 240.0) > tolerance:
        raise ValueError(f"regulation rotation must sum to 240 minutes, got {total:.2f}")
    if any(p.minutes < 0 or p.minutes > 48 for p in rows):
        raise ValueError("invalid player minutes")
    return rows


def redistribute_out_minutes(players: Iterable[RotationPlayer]) -> list[RotationPlayer]:
    """Redistribute unavailable minutes across available players by existing role size.

    This is deliberately conservative and capped at 42 projected minutes per player.
    A future learned rotation challenger can replace it only after validation.
    """
    rows = list(players)
    unavailable = {"OUT", "DOUBTFUL"}
    lost = sum(p.minutes for p in rows if p.status.upper() in unavailable)
    available = [p for p in rows if p.status.upper() not in unavailable]
    if not available:
        raise ValueError("no available players for minute redistribution")
    base = sum(p.minutes for p in available)
    if base <= 0:
        raise ValueError("available rotation has no minutes")
    out: list[RotationPlayer] = []
    for p in rows:
        if p.status.upper() in unavailable:
            out.append(RotationPlayer(p.player_id, p.name, 0.0, p.offensive_impact, p.defensive_impact, p.usage, p.status))
            continue
        share = p.minutes / base
        minutes = min(42.0, p.minutes + lost * share)
        out.append(RotationPlayer(p.player_id, p.name, minutes, p.offensive_impact, p.defensive_impact, p.usage, p.status))
    total = sum(p.minutes for p in out)
    deficit = 240.0 - total
    if abs(deficit) > 1e-9:
        candidates = sorted(range(len(out)), key=lambda i: out[i].minutes, reverse=True)
        for i in candidates:
            room = 42.0 - out[i].minutes if deficit > 0 else out[i].minutes
            delta = max(-room, min(room, deficit))
            if abs(delta) <= 1e-12:
                continue
            p = out[i]
            out[i] = RotationPlayer(p.player_id, p.name, p.minutes + delta, p.offensive_impact, p.defensive_impact, p.usage, p.status)
            deficit -= delta
            if abs(deficit) < .01:
                break
    return validate_rotation(out)
