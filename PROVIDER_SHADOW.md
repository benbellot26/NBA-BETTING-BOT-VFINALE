# Official gamebook provider shadow

Pulsar NBA keeps `OfficialNBAProvider` as the only production provider
boundary. The official scorer gamebook path is a separate research shadow and
cannot authorize a prediction source, a bet, a stake or certification.

## Why it exists

Hosted GitHub runners currently reach the official NBA Communications schedule
and official scorer gamebook PDFs, while `stats.nba.com` can time out. The
gamebook shadow lets the project collect prospective evidence for an alternate
source without silently replacing the canonical provider.

## Inputs

For each target date the shadow uses only information available before tipoff:

- official NBA Communications schedule;
- official scorer gamebooks from dates strictly before the target date;
- official NBA injury report;
- the same team-strength, schedule-context, rotation and structural model code
  used by V1.

The gamebook history must be 100% complete for the requested cutoff. Each team
must have at least five completed games. Both target-game injury submissions
must be present. Forecasts are recorded only 5–30 minutes before tipoff.

No odds, lines, bookmaker prices or Pinnacle values are fetched or used.

## Evidence

The prospective ledger is:

    runtime/provider_shadow/gamebook_forecasts.jsonl

Each row is immutable research evidence with:

- `role=ALTERNATE_PROVIDER_SHADOW`;
- `production_provider_authorized=false`;
- `predictive_authority=false`;
- `market_data_used=false`;
- `promoted=false`;
- `betting_certified=false`.

Postgame scoring uses the official scorer gamebook for the final result:

    python -m nba.gamebook_shadow_performance

The report tracks margin MAE, total MAE and ML Brier/LogLoss/ECE. Whenever a
canonical V1 FINAL forecast exists for the same date/home/away matchup, the
report also calculates paired V1 and shadow MAE/Brier values.

The report always remains `MANUAL_REVIEW_ONLY`. There is deliberately no
automatic provider-promotion gate in this generation.

## Workflow

The **Pulsar NBA Gamebook Provider Shadow** workflow can always be launched
manually. Scheduled runs execute only when the repository variable
`NBA_PROVIDER_SHADOW_ENABLED=true`.

It makes no Odds API request and is independent of `NBA_LIVE_ENABLED`.

A future promotion would require a new frozen provider generation, explicit
human review and fresh prospective validation. This shadow evidence alone does
not modify `OfficialNBAProvider`.
