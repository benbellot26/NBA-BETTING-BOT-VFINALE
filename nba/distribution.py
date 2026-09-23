from __future__ import annotations

import math

from .model import ProbabilitySurface, ScoreProjection


def normal_cdf(x: float) -> float:
    return .5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def probability_surface(projection: ScoreProjection, *, spread_line: float, total_line: float) -> ProbabilitySurface:
    p = projection.validated()
    # spread_line uses the standard home-team notation: -4.5 means home must win by >4.5.
    home_ml = normal_cdf(p.margin_mean / p.margin_sd)
    home_cover = normal_cdf((p.margin_mean + spread_line) / p.margin_sd)
    over = normal_cdf((p.total_mean - total_line) / p.total_sd)
    return ProbabilitySurface(
        home_ml=home_ml,
        away_ml=1-home_ml,
        home_spread=home_cover,
        away_spread=1-home_cover,
        over=over,
        under=1-over,
        spread_line=float(spread_line),
        total_line=float(total_line),
    ).validated()
