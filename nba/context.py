from __future__ import annotations

from .model import GameContext

HOME_COURT_POINTS_PER100 = 1.35


def context_adjustments(context: GameContext) -> dict[str, float]:
    home = HOME_COURT_POINTS_PER100
    away = 0.0
    if context.home_b2b:
        home -= .65
    if context.away_b2b:
        away -= .65
    if context.home_three_in_four:
        home -= .30
    if context.away_three_in_four:
        away -= .30
    home -= min(.75, max(0.0, context.home_travel_km - 750.0) / 4000.0)
    away -= min(.75, max(0.0, context.away_travel_km - 750.0) / 4000.0)
    home -= min(.50, abs(context.home_timezone_shift) * .15)
    away -= min(.50, abs(context.away_timezone_shift) * .15)
    if context.altitude_m >= 1200:
        home += .20
        away -= .20
    return {"home_per100": home, "away_per100": away}
