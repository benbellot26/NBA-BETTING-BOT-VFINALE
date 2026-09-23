# Pulsar NBA — Probability & Decision Engine

Pulsar NBA is a standalone NBA research engine inspired by the governance discipline of Pulsar MLB while using an entirely separate basketball model.

## Current status

**V1.0.0 is RESEARCH ONLY.** The repository deliberately cannot represent itself as betting-certified without prospective evidence passing `nba.certification`.

## Core calculations

For each game the engine estimates:

- projected possessions;
- opponent-adjusted offensive efficiency for each team;
- bounded matchup effects (3PA profile, rim pressure, turnovers, offensive rebounding, transition);
- home court, rest, back-to-back, 3-in-4, travel, timezone and altitude context;
- player availability and rotation uncertainty;
- projected home/away score, margin and total;
- Moneyline, Spread and Total probabilities;
- conservative uncertainty intervals;
- executable breakeven probability, model edge, robust edge, Pinnacle no-vig edge and robust sharp edge;
- conservative quarter-Kelly staking under portfolio caps.

Market prices are post-model data and never enter the basketball probability calculation.

## Package map

- `nba/team_strength.py` — shrinkage and opponent-adjusted efficiency.
- `nba/pace.py` — pace projection.
- `nba/rotations.py` — 240-minute rotation contract and redistribution.
- `nba/player_availability.py` — OUT/DOUBTFUL/QUESTIONABLE/PROBABLE/AVAILABLE effects.
- `nba/matchup.py` — bounded style interactions.
- `nba/context.py` — home/rest/travel/timezone/altitude context.
- `nba/structural.py` — score construction.
- `nba/distribution.py` — ML/spread/total probability surface.
- `nba/market.py` — execution line shopping and Pinnacle no-vig.
- `nba/uncertainty.py` — fail-safe probability bands.
- `nba/decision.py` — fail-closed market-specific decision diagnostics.
- `nba/staking.py` — lower-bound quarter Kelly and exposure caps.
- `nba/performance.py` — Brier, LogLoss, ECE and MAE.
- `nba/certification.py` — prospective evidence gate.
- `nba/tracking.py` — immutable-style JSONL helpers and CLV calculations.
- `nba/research.py` — sensitivity/ablation helpers.
- `nba/acquisition.py` — live The Odds API client plus fixture loading.
- `nba/pipeline.py` — end-to-end analysis.
- `nba/discord.py` — human-readable game report formatting.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Live odds

Set `ODDS_API_KEY` and call `nba.acquisition.fetch_nba_odds()`. Team/player statistical acquisition is intentionally provider-agnostic in V1; normalized point-in-time inputs can be supplied without coupling prediction logic to one vendor.

## Certification philosophy

Software readiness is not betting readiness. V1 begins uncertified. The current gate requires, per market, sufficient prospective sample, calibration, paired sharp evidence and CLV evidence. Thresholds are code-visible and should not be lowered merely to create more bets.
