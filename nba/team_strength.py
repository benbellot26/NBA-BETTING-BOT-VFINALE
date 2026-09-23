from __future__ import annotations

from dataclasses import dataclass

from .model import TeamMetrics

LEAGUE_ORTG = 115.0
LEAGUE_DRTG = 115.0
LEAGUE_PACE = 99.5


@dataclass(frozen=True)
class TimeWindow:
    season: float
    last30: float | None = None
    last15: float | None = None
    last10: float | None = None
    last5: float | None = None


def shrink(values: TimeWindow, *, league_mean: float, season_weight: float = .55) -> float:
    """Bound recent form so small hot/cold samples cannot dominate season talent."""
    recent = [(values.last30, .18), (values.last15, .12), (values.last10, .08), (values.last5, .03)]
    total = season_weight
    acc = season_weight * values.season
    for value, weight in recent:
        if value is not None:
            acc += weight * value
            total += weight
    prior_weight = max(0.0, 1.0 - total)
    acc += prior_weight * league_mean
    return acc / max(1e-12, total + prior_weight)


def adjusted_efficiency(attack_ortg: float, opponent_drtg: float, *, league_ortg: float = LEAGUE_ORTG, attack_power: float = .58, defense_power: float = .42) -> float:
    attack_ratio = max(.70, min(1.30, attack_ortg / league_ortg))
    defense_ratio = max(.70, min(1.30, opponent_drtg / league_ortg))
    return league_ortg * attack_ratio**attack_power * defense_ratio**defense_power


def blend_team_metrics(team: str, *, ortg: TimeWindow, drtg: TimeWindow, pace: TimeWindow, style: dict[str, float] | None = None, home: bool = False) -> TeamMetrics:
    style = style or {}
    return TeamMetrics(
        team=team,
        ortg=shrink(ortg, league_mean=LEAGUE_ORTG),
        drtg=shrink(drtg, league_mean=LEAGUE_DRTG),
        pace=shrink(pace, league_mean=LEAGUE_PACE),
        efg=float(style.get("efg", .55)),
        tov_pct=float(style.get("tov_pct", .13)),
        orb_pct=float(style.get("orb_pct", .25)),
        ft_rate=float(style.get("ft_rate", .25)),
        three_pa_rate=float(style.get("three_pa_rate", .40)),
        rim_rate=float(style.get("rim_rate", .30)),
        transition_rate=float(style.get("transition_rate", .15)),
        home=home,
    ).validated()
