# Pinnacle market diagnostics

Pinnacle remains the only sharp benchmark used by the NBA research pipeline.
No other bookmaker or market consensus can replace it.

## Targeted smoke states

The daily targeted request uses `bookmakers=pinnacle` and classifies:

- `NO_NBA_EVENTS`: the odds provider returned no NBA events;
- `PINNACLE_TARGET_EMPTY`: NBA events were returned but every event had an
  empty bookmaker list in the targeted Pinnacle request;
- `PINNACLE_ABSENT`: bookmakers were returned but Pinnacle was not among them;
- `PINNACLE_PARTIAL`: Pinnacle exists but does not expose a paired
  ML/Spread/Total contract on at least one event;
- `PINNACLE_READY`: at least one event exposes all three paired contracts.

The report also records raw event/bookmaker counts and fresh paired-market
counts, so transport availability is distinguishable from stale/partial market
coverage.

## Availability history

Each daily smoke can append a compact immutable row to:

    runtime/market_availability.jsonl

and refresh:

    runtime/market_availability_summary.json

The summary tracks the latest state and consecutive not-ready observations.
This history is diagnostic only and never changes the benchmark.

## Close failures

Close capture now returns structured failure counts while preserving the
existing human-readable failure strings. Codes include:

- `PINNACLE_ABSENT`
- `PINNACLE_STALE`
- `CONTRACT_MISSING`
- `EVENT_NOT_FOUND`
- `TIMING_INVALID`
- `ODDS_PROVIDER_ERROR`

These codes help separate provider availability problems from line-contract or
timing problems. They do not relax any close-evidence requirement.


## Consensus quality diagnostics

The evaluation-only consensus benchmark now reports descriptive quality context
alongside Brier/LogLoss/ECE:

- mean / median / min / max contributing bookmaker count;
- mean / median / p90 / max no-vig probability dispersion;
- mean signed model-minus-consensus probability gap;
- mean absolute model-consensus probability gap;
- direction-disagreement rate around the 50% decision boundary.

These fields are descriptive only. No dispersion threshold, bookmaker-count
threshold beyond the existing minimum of three, or consensus result can alter
betting certification. Pinnacle remains the unique sharp benchmark.


## Regular vs preseason NBA sport keys

The Odds API exposes regular-season NBA and NBA preseason under distinct sport
keys. Pulsar therefore keeps production regular-season acquisition on
`basketball_nba`, while deep diagnostics may explicitly probe either:

- `basketball_nba`
- `basketball_nba_preseason`

The ordinary daily market smoke is unchanged and still costs one request.
It does not auto-switch sport keys.

## Deep Pinnacle transport probe

The manual **Pulsar NBA Pinnacle Deep Diagnostic** workflow compares two current
requests for the same selected sport key:

1. targeted `bookmakers=pinnacle`;
2. regional `regions=eu`.

This distinguishes:

- `TARGETED_PINNACLE_READY`: targeted Pinnacle has a complete featured-market event;
- `TARGETED_PINNACLE_PARTIAL`: Pinnacle exists but lacks full paired coverage;
- `TARGET_FILTER_MISMATCH`: the targeted query is empty/absent while the EU
  regional response contains Pinnacle;
- `PINNACLE_NOT_CURRENTLY_LISTED`: EU events exist but Pinnacle is absent;
- `NO_EVENTS_FOR_SPORT_KEY`: neither query returns events;
- `REGIONAL_MARKET_EMPTY`: targeted/region responses exist in an unusable state.

This probe is diagnostic only. It never changes `coverage_ready`, the sharp
benchmark, or certification.

## Historical Pinnacle probe

Historical access remains handled by the existing **Pulsar NBA Historical
Pinnacle Probe** workflow and `nba.historical_pinnacle_probe`. It targets a
known past NBA game, records paired Pinnacle market availability and safely
persists provider plan errors such as historical access being unavailable.

The deep current transport probe and the historical probe are intentionally
separate: current diagnostics may use either regular or preseason sport keys,
while historical research keeps its established known-game contract. Neither
can replace current Pinnacle quotes for decisions or CLV capture.
