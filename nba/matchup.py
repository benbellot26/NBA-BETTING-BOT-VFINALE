from __future__ import annotations

from .model import TeamMetrics


def matchup_adjustment(attack: TeamMetrics, defense: TeamMetrics) -> tuple[float, dict[str, float]]:
    three = (attack.three_pa_rate - .40) * 5.0 * (defense.efg - .55)
    rim = (attack.rim_rate - .30) * 4.0 * (defense.drtg - 115.0) / 10.0
    turnovers = -(attack.tov_pct - .13) * 18.0 * max(.5, min(1.5, defense.drtg / 115.0))
    rebounding = (attack.orb_pct - .25) * 8.0
    transition = (attack.transition_rate - .15) * 6.0
    raw = three + rim + turnovers + rebounding + transition
    bounded = max(-2.5, min(2.5, raw))
    return bounded, {
        "three": three,
        "rim": rim,
        "turnovers": turnovers,
        "rebounding": rebounding,
        "transition": transition,
        "bounded": bounded,
    }
