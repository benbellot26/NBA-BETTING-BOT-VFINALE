from __future__ import annotations

from dataclasses import replace
from typing import Callable

from .model import ScoreProjection


def sensitivity(projection: ScoreProjection, *, pct: float = .10) -> dict[str, ScoreProjection]:
    """Read-only distribution sensitivity. It cannot authorize a wager."""
    p=projection.validated()
    return {
        "margin_sd_down": replace(p, margin_sd=max(5.0,p.margin_sd*(1-pct))),
        "margin_sd_up": replace(p, margin_sd=p.margin_sd*(1+pct)),
        "total_sd_down": replace(p, total_sd=max(7.0,p.total_sd*(1-pct))),
        "total_sd_up": replace(p, total_sd=p.total_sd*(1+pct)),
    }


def ablation(base_builder: Callable[..., ScoreProjection], variants: dict[str, dict]) -> dict[str, ScoreProjection]:
    return {name: base_builder(**kwargs) for name,kwargs in variants.items()}
