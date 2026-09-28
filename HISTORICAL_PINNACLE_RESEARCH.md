# Historical Pinnacle research

This path exists only to recover a research benchmark when the current odds
feed does not expose Pinnacle. It never rewrites prospective forecasts and it
never counts toward betting certification.

## Recovery

For each immutable FINAL forecast, the recovery process groups rows by their
original `forecast_at` timestamp and queries the historical NBA odds endpoint
with `bookmakers=pinnacle`.

A recovered snapshot is accepted only when:

- the provider timestamp is at or before the original forecast;
- it is no more than 15 minutes older than that forecast;
- the event matches the same home/away teams and tipoff;
- Pinnacle exposes a valid paired contract at the exact stored spread/total
  line;
- the Pinnacle quote itself is fresh relative to the original forecast.

Recovered probabilities are written to:

    runtime/research/pinnacle_historical_entry.jsonl

The original forecast JSONL is never modified.

## Scoring

Run:

    python -m nba.historical_pinnacle_performance

This scores V1 and recovered Pinnacle on the exact same resolved contracts for
ML, Spread and Total using Brier, LogLoss and ECE.

All output is explicitly:

- `role=HISTORICAL_EVALUATION_ONLY`;
- `market_data_used_as_model_feature=false`;
- `used_for_certification=false`;
- `pinnacle_replacement=false`;
- `betting_certified=false`.

This evidence can answer research questions such as whether V1 was closer to
outcomes than the historical Pinnacle entry snapshot. It cannot satisfy a
prospective sharp-benchmark requirement because the historical snapshot was
retrieved later.

## Cost control

The workflow **Pulsar NBA Historical Pinnacle Research** is disabled on its
schedule unless `NBA_HISTORICAL_PINNACLE_ENABLED=true`. It may always be
launched manually.

Each unique forecast timestamp can cost one historical Odds API request.
`--max-snapshots` limits requests per run, and every request still passes
through the repository odds-budget ledger.
