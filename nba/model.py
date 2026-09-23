from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from . import MODEL_GENERATION, PROBABILITY_POLICY_ID, ROLE, SCHEMA, VERSION


def _finite(value: Any, name: str) -> float:
    try:
        out = float(value)
    except Exception as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite")
    return out


@dataclass(frozen=True)
class TeamMetrics:
    team: str
    ortg: float
    drtg: float
    pace: float
    efg: float = .55
    tov_pct: float = .13
    orb_pct: float = .25
    ft_rate: float = .25
    three_pa_rate: float = .40
    rim_rate: float = .30
    transition_rate: float = .15
    home: bool = False

    def validated(self) -> "TeamMetrics":
        if not self.team:
            raise ValueError("team is required")
        if not 80 <= _finite(self.ortg, "ortg") <= 140:
            raise ValueError("ortg outside supported NBA range")
        if not 80 <= _finite(self.drtg, "drtg") <= 140:
            raise ValueError("drtg outside supported NBA range")
        if not 80 <= _finite(self.pace, "pace") <= 120:
            raise ValueError("pace outside supported NBA range")
        return self


@dataclass(frozen=True)
class GameContext:
    game_id: str
    game_date: str
    analyzed_at: str
    home: str
    away: str
    home_rest_days: float = 1.0
    away_rest_days: float = 1.0
    home_b2b: bool = False
    away_b2b: bool = False
    home_three_in_four: bool = False
    away_three_in_four: bool = False
    home_travel_km: float = 0.0
    away_travel_km: float = 0.0
    home_timezone_shift: float = 0.0
    away_timezone_shift: float = 0.0
    altitude_m: float = 0.0
    phase: str = "EARLY"


@dataclass(frozen=True)
class ScoreProjection:
    game_id: str
    game_date: str
    analyzed_at: str
    home: str
    away: str
    home_points: float
    away_points: float
    possessions: float
    margin_mean: float
    total_mean: float
    margin_sd: float = 11.5
    total_sd: float = 17.0
    phase: str = "EARLY"
    data_quality: str = "UNKNOWN"

    def validated(self) -> "ScoreProjection":
        if not self.game_id or not self.home or not self.away:
            raise ValueError("game_id/home/away required")
        for name in ("home_points", "away_points", "possessions", "margin_sd", "total_sd"):
            if _finite(getattr(self, name), name) <= 0:
                raise ValueError(f"{name} must be > 0")
        if abs((self.home_points - self.away_points) - self.margin_mean) > 1e-6:
            raise ValueError("margin_mean inconsistent with projected scores")
        if abs((self.home_points + self.away_points) - self.total_mean) > 1e-6:
            raise ValueError("total_mean inconsistent with projected scores")
        return self


@dataclass(frozen=True)
class ProbabilitySurface:
    home_ml: float
    away_ml: float
    home_spread: float
    away_spread: float
    over: float
    under: float
    spread_line: float
    total_line: float

    def validated(self, tol: float = 1e-9) -> "ProbabilitySurface":
        for key in ("home_ml", "away_ml", "home_spread", "away_spread", "over", "under"):
            value = _finite(getattr(self, key), key)
            if not 0 <= value <= 1:
                raise ValueError(f"invalid probability {key}={value}")
        for a, b, label in ((self.home_ml, self.away_ml, "ML"), (self.home_spread, self.away_spread, "SPREAD"), (self.over, self.under, "TOTAL")):
            if abs(a + b - 1.0) > tol:
                raise ValueError(f"non-complementary probabilities for {label}")
        return self


def prediction_payload(projection: ScoreProjection, surface: ProbabilitySurface, *, components: dict[str, Any] | None = None) -> dict[str, Any]:
    p = projection.validated()
    s = surface.validated()
    return {
        "schema": SCHEMA,
        "software_version": VERSION,
        "model_generation": MODEL_GENERATION,
        "probability_policy_id": PROBABILITY_POLICY_ID,
        "role": ROLE,
        "market_probability_used_as_feature": False,
        "game_id": p.game_id,
        "game_date": p.game_date,
        "analyzed_at": p.analyzed_at,
        "phase": p.phase,
        "home": p.home,
        "away": p.away,
        "score_projection": asdict(p),
        "probabilities": asdict(s),
        "components": components or {},
    }
