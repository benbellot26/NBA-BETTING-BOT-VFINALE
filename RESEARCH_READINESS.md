# Research readiness matrix

`python -m nba.research_readiness` produces one compact status document:

    runtime/research_readiness.json

It summarizes the independent research tracks without granting authority to any
of them.

## Areas

### Canonical provider

Reports whether the official production input path is operational and surfaces
the current schedule, stats and injury states.

### Current Pinnacle

Reports the targeted current-market state, current Pinnacle event count,
regional discovery state and the number of complete evaluation-only consensus
events. Other bookmakers never replace Pinnacle.

### Historical Pinnacle research

Reads the persisted historical-access probe. When The Odds API reports
`HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN`, the historical recovery module
returns `SKIPPED_ACCESS_BLOCKED` before reserving an Odds API request.

This avoids repeatedly spending the repository request budget on an endpoint
the current account cannot use.

### Official gamebook provider shadow

Tracks official-scorer-gamebook history and the prospective alternate-provider
manual review gate. It remains isolated from `OfficialNBAProvider`.

### Learned V2

Tracks enriched PIT FINAL forecasts, prospective shadow predictions and the
manual model-review gate. V2 remains SHADOW until explicit future review.

## Authority boundary

The matrix always reports:

- `role=RESEARCH_STATUS_ONLY`;
- `live_betting_authorized=false`;
- `betting_certified=false`;
- `benchmark_bookmaker=pinnacle`;
- `pinnacle_replacement_allowed=false`.

A green research area means that area has enough evidence for its next research
step. It does not authorize betting, provider promotion or model promotion.
