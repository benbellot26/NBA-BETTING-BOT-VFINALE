from __future__ import annotations

from typing import Any, Iterable

from .context import context_adjustments
from .matchup import matchup_adjustment
from .model import GameContext, ScoreProjection, TeamMetrics
from .pace import projected_pace
from .player_availability import rotation_adjustment
from .rotations import RotationPlayer
from .team_strength import adjusted_efficiency


def project_game(
    *,
    home: TeamMetrics,
    away: TeamMetrics,
    context: GameContext,
    home_rotation: Iterable[RotationPlayer] | None = None,
    away_rotation: Iterable[RotationPlayer] | None = None,
) -> tuple[ScoreProjection, dict[str, Any]]:
    home = home.validated(); away = away.validated()
    possessions, pace_meta = projected_pace(home, away, context)
    h_base = adjusted_efficiency(home.ortg, away.drtg)
    a_base = adjusted_efficiency(away.ortg, home.drtg)
    h_match, h_match_meta = matchup_adjustment(home, away)
    a_match, a_match_meta = matchup_adjustment(away, home)
    ctx = context_adjustments(context)
    h_av = rotation_adjustment(home_rotation) if home_rotation else None
    a_av = rotation_adjustment(away_rotation) if away_rotation else None
    h_eff = h_base + h_match + ctx["home_per100"] + (h_av.offense_per100 if h_av else 0.0) - (a_av.defense_per100 if a_av else 0.0)
    a_eff = a_base + a_match + ctx["away_per100"] + (a_av.offense_per100 if a_av else 0.0) - (h_av.defense_per100 if h_av else 0.0)
    home_points = possessions * h_eff / 100.0
    away_points = possessions * a_eff / 100.0
    margin_sd = 11.5 + .20 * ((h_av.uncertainty_pp if h_av else 0.0) + (a_av.uncertainty_pp if a_av else 0.0))
    total_sd = 17.0 + .25 * ((h_av.uncertainty_pp if h_av else 0.0) + (a_av.uncertainty_pp if a_av else 0.0))
    projection = ScoreProjection(
        game_id=context.game_id,
        game_date=context.game_date,
        analyzed_at=context.analyzed_at,
        home=context.home,
        away=context.away,
        home_points=home_points,
        away_points=away_points,
        possessions=possessions,
        margin_mean=home_points-away_points,
        total_mean=home_points+away_points,
        margin_sd=margin_sd,
        total_sd=total_sd,
        phase=context.phase,
        data_quality="GOOD" if not ((h_av and h_av.unresolved_key_player) or (a_av and a_av.unresolved_key_player)) else "LINEUP_UNCERTAIN",
    ).validated()
    return projection, {
        "home_base_efficiency": h_base,
        "away_base_efficiency": a_base,
        "home_matchup": h_match_meta,
        "away_matchup": a_match_meta,
        "pace": pace_meta,
        "context": ctx,
        "home_availability": None if h_av is None else {"offense_per100": h_av.offense_per100, "defense_per100": h_av.defense_per100, "uncertainty_pp": h_av.uncertainty_pp, "unresolved_key_player": h_av.unresolved_key_player},
        "away_availability": None if a_av is None else {"offense_per100": a_av.offense_per100, "defense_per100": a_av.defense_per100, "uncertainty_pp": a_av.uncertainty_pp, "unresolved_key_player": a_av.unresolved_key_player},
    }
