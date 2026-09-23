from __future__ import annotations

from typing import Any


def format_game(payload: dict[str,Any]) -> str:
    p=payload["score_projection"]; probs=payload["probabilities"]
    lines=[
        f"🏀 {payload['away']} @ {payload['home']}",
        "",
        "PROJECTED SCORE",
        f"{payload['away']} {p['away_points']:.1f}",
        f"{payload['home']} {p['home_points']:.1f}",
        f"Projected total: {p['total_mean']:.1f}",
        f"Projected margin: {payload['home']} {p['margin_mean']:+.1f}",
        "",
        f"ML: {payload['home']} {probs['home_ml']:.1%} | {payload['away']} {probs['away_ml']:.1%}",
        f"Spread {probs['spread_line']:+.1f}: HOME {probs['home_spread']:.1%} | AWAY {probs['away_spread']:.1%}",
        f"Total {probs['total_line']:.1f}: O {probs['over']:.1%} | U {probs['under']:.1%}",
    ]
    for c in (payload.get("decision") or {}).get("candidates") or []:
        lines.extend(["",f"{c['market']} {c['selection']} @ {c['price']:.2f} — {c['status']}",f"Edge {c['model_edge_pp']:+.2f} pp | Robust {c['robust_edge_pp']:+.2f} pp"])
        if c.get("failures"): lines.append("Reason: "+", ".join(c["failures"]))
    return "\n".join(lines)
