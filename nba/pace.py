from __future__ import annotations

from .model import GameContext, TeamMetrics


def projected_pace(home: TeamMetrics, away: TeamMetrics, context: GameContext) -> tuple[float, dict[str, float]]:
    base = 2.0 / (1.0 / home.pace + 1.0 / away.pace)
    rest = 0.0
    if context.home_b2b and context.away_b2b:
        rest -= .35
    elif context.home_b2b or context.away_b2b:
        rest -= .15
    schedule = -.15 * int(context.home_three_in_four) - .15 * int(context.away_three_in_four)
    value = max(90.0, min(108.0, base + rest + schedule))
    return value, {"base": base, "rest_adjustment": rest, "schedule_adjustment": schedule}
