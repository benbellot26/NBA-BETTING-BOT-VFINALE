# Pulsar NBA — Probability & Decision Engine

Pulsar NBA is a standalone NBA probability, market, research and decision engine. It is independent from the MLB repository and shares governance principles, not baseball coefficients.

## Current status

**V1.1.1 — RESEARCH ONLY.** Software readiness does not imply betting certification. The authoritative source state in `data/nba_betting_certification.json` starts uncertified, and runtime evidence can only produce a certification candidate after the prospective gates are satisfied.

## End-to-end chain

`official schedule + NBA.com stats + official injury report -> frozen basketball model -> ML/spread/total probabilities -> uncertainty -> executable odds -> Pinnacle no-vig -> paper cohort -> close/CLV -> settlement -> certification`

Market prices are post-model data. They never enter the basketball probability calculation.

## Basketball model

The V1 structural generation models:

- season/recent opponent-adjusted OffRtg and DefRtg with shrinkage;
- projected possessions and pace;
- eFG%, turnovers, offensive rebounding, free-throw rate and 3PA profile;
- bounded matchup interactions;
- home court, rest, back-to-back, 3-in-4, travel, timezone and altitude;
- projected 240-minute rotations;
- official player availability statuses and lineup uncertainty;
- projected home/away score, margin and total;
- separate uncertainty for margin and total;
- Moneyline, Spread and Total probability surfaces.

## Decision layer

For every executable selection the engine calculates:

- model probability;
- conservative lower probability;
- breakeven probability;
- raw model edge;
- robust edge;
- Pinnacle no-vig probability;
- sharp edge and robust sharp edge;
- execution book/price;
- fail-closed reasons.

A candidate can be `paper_eligible` while the system is still uncertified. A real `BET` additionally requires market certification and the FINAL 5-30 minute timing window.

## Prospective evidence

The isolated `runtime-data` branch stores mutable evidence separately from source code:

- immutable input snapshots;
- paper candidates;
- Pinnacle close captures;
- settled paper outcomes;
- CLV;
- Brier / LogLoss / ECE;
- paired model-vs-sharp evidence;
- certification candidate state.

System/paper ROI is hypothetical and must not be represented as realized user ROI.

## Main modules

- `nba/team_strength.py` — temporal shrinkage and team strength.
- `nba/pace.py` — pace projection.
- `nba/rotations.py`, `nba/rotation_projection.py` — 240-minute rotation engine.
- `nba/player_availability.py`, `nba/injury_pdf.py` — PIT injury/availability handling.
- `nba/schedule.py`, `nba/schedule_context.py` — official schedule, rest, travel and timezone.
- `nba/nba_stats_api.py`, `nba/team_inputs.py` — NBA.com statistical acquisition.
- `nba/structural.py`, `nba/distribution.py` — score and probability generation.
- `nba/market.py`, `nba/odds_normalizer.py` — execution and Pinnacle no-vig.
- `nba/uncertainty.py`, `nba/decision.py` — conservative decision gate.
- `nba/staking.py`, `nba/portfolio_correlation.py` — lower-bound quarter Kelly and exposure caps.
- `nba/prospective.py`, `nba/close_runtime.py`, `nba/performance_runtime.py` — prospective evidence chain.
- `nba/certification.py` — market-specific certification gate.
- `nba/challengers.py`, `nba/research_registry.py` — shadow research/governance.
- `nba/provider_smoke.py`, `nba/preflight.py` — provider and software health checks.

## Automated workflows

- **Pulsar NBA CI** — install, compile, preflight and unit tests on `main`.
- **Pulsar NBA Provider Smoke** — daily health check of official schedule/stats/injury sources.
- **Pulsar NBA Live Research** — scheduled pregame analysis, paper cohort and live Pinnacle close capture.
- **Pulsar NBA Daily Evidence** — settlement and performance/certification refresh.

## Setup

Python 3.12 is the runtime contract. The basketball core is standard-library-only; official injury PDF acquisition uses pinned `pypdf==6.19.0`.

Configure the repository secret `ODDS_API_KEY` for live odds. No credential is committed.

## Commands

    python -m pip install .
    python -m nba.preflight
    python -m unittest discover -s tests -v
    python -m nba.provider_smoke
    python -m nba.live_runtime
    python -m nba.close_runtime --mode live
    python -m nba.performance_runtime

Historical Pinnacle close recovery is available with `python -m nba.close_runtime --mode historical` when the Odds API subscription supports historical data.

See `ARCHITECTURE.md` and `RUNBOOK.md`.
