from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .rotations import RotationPlayer, redistribute_out_minutes

STATUS_ACTIVE_PROB = {
    "AVAILABLE": 1.00,
    "PROBABLE": .90,
    "QUESTIONABLE": .50,
    "DOUBTFUL": .15,
    "OUT": 0.00,
}


@dataclass(frozen=True)
class AvailabilityAdjustment:
    offense_per100: float
    defense_per100: float
    uncertainty_pp: float
    unresolved_key_player: bool
    projected_rotation: tuple[RotationPlayer, ...]


def rotation_adjustment(players: Iterable[RotationPlayer], *, key_impact_threshold: float = 3.0) -> AvailabilityAdjustment:
    original = list(players)
    projected = redistribute_out_minutes(original)
    offense = 0.0
    defense = 0.0
    uncertainty = 0.0
    unresolved = False
    for p in original:
        status = p.status.upper()
        active_p = STATUS_ACTIVE_PROB.get(status, .50)
        minute_share = max(0.0, p.minutes) / 48.0
        lost = 1.0 - active_p
        offense -= p.offensive_impact * minute_share * lost
        defense -= p.defensive_impact * minute_share * lost
        if status in {"QUESTIONABLE", "DOUBTFUL"}:
            impact = abs(p.offensive_impact) + abs(p.defensive_impact)
            uncertainty += min(2.5, .35 * impact * minute_share)
            if impact >= key_impact_threshold:
                unresolved = True
    return AvailabilityAdjustment(
        offense_per100=offense,
        defense_per100=defense,
        uncertainty_pp=min(5.0, uncertainty),
        unresolved_key_player=unresolved,
        projected_rotation=tuple(projected),
    )
