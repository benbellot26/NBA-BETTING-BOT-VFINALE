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
