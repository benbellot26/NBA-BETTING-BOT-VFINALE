# Pulsar NBA runbook

## Repository boundaries

Source code and frozen reference state live on main. Mutable prospective evidence lives on runtime-data. Do not merge runtime-data into main.

## Required secret

ODDS_API_KEY is required by the live research workflow. Store it in GitHub repository Actions secrets. Never commit it to a file.

## Scheduled flow

Pulsar NBA Live Research runs every 20 minutes during the usual NBA game window in UTC. It hydrates the prior runtime-data state, runs the live model, records FINAL paper-eligible candidates, captures a near-close Pinnacle snapshot when available, uploads an artifact, then persists runtime back to runtime-data.

Pulsar NBA Daily Evidence runs once per day. It settles completed paper entries from the official NBA schedule, joins captured closes, refreshes proper scores and CLV diagnostics, and writes a certification candidate.

Pulsar NBA Provider Smoke checks the official schedule, NBA.com team stats and the official injury-report feed once per day.

## Fail-closed rules

No real BET is authorized if any of these conditions fail:

- market-specific betting certification;
- FINAL timing window of 5-30 minutes before tip;
- valid official schedule match;
- usable NBA team/player stats;
- official injury report parsed successfully;
- rotation construction;
- fresh executable market;
- paired Pinnacle no-vig benchmark;
- model edge threshold;
- conservative lower-bound edge threshold;
- robust sharp-edge threshold;
- resolved key-player uncertainty.

Missing data produces NO_ANALYSIS or NO_BET rather than silently substituting a weaker source.

## Paper cohort

Before certification, candidates that clear every operational, uncertainty and sharp-market condition can be marked paper_eligible. They remain NO_BET. One entry per game/market/selection is stored prospectively.

Paper staking is hypothetical. It uses the same conservative lower-bound quarter-Kelly logic and exposure caps, but it is not user execution and must not be reported as realized return.

## Closing prices

The normal path captures Pinnacle shortly before tip using current odds.

If a close is missed and the Odds API plan provides historical access, run:

    python -m nba.close_runtime --mode historical

Historical featured-market snapshots are a paid Odds API feature. The historical endpoint returns the closest snapshot at or before the requested timestamp. A later postgame price must never be substituted for a missing close.

## Certification

The runtime certification candidate is written to runtime/evidence/certification_candidate.json on runtime-data.

Current minimum evidence is intentionally strict:

- at least 600 independent games globally;
- at least 400 settled observations per market;
- ECE no greater than 0.05;
- at least 400 paired sharp observations per market;
- at least 100 comparable CLV observations per market;
- positive CLV rate of at least 0.52.

These are necessary gates, not proof of profitability. Predictive changes require a new generation/policy decision and prospective validation.

## Manual health commands

    python -m nba.preflight
    python -m unittest discover -s tests -v
    python -m nba.provider_smoke

## Season timing

The 2026-27 regular season begins October 20, 2026. Before regular-season data exists, empty current-season stats should not be treated as evidence. The provider smoke may use the previous season only to verify that the upstream stats endpoint is healthy; production predictions remain point-in-time to their target season.

## Verification after adding an odds key

The Odds Key Smoke workflow runs once when its script/workflow is merged into
main. It makes one authenticated sports-catalog request, logging only an
authorization boolean and sport count. Check its GitHub Actions result.
A successful check does NOT establish access to NBA spreads/totals, Pinnacle
or historical snapshots; those require live provider coverage and plan support.

## PIT training data and research V2

FINAL forecasts are retained in runtime/evidence/final_forecasts.jsonl even
when no paper bets meet the decision thresholds. The daily settlement workflow
writes independently observed outcomes to final_outcomes.jsonl. Generate the
joined corpus only after both exist:

    python -m nba.replay_export

Then choose chronological, pre-registered train and holdout cutoffs:

    python -m nba.v2_shadow --input runtime/research/pit_dataset.jsonl --train-cutoff 2027-01-01T00:00:00Z --holdout-start 2027-01-02T00:00:00Z

The V2 result is SHADOW and cannot change the live decision code. Do not
present synthetic tests or historical data downloaded today as true archived
point-in-time performance.

## Operational stop after provider smoke (23 September 2026)

The Odds API secret is valid (non-billable sports-catalog test passed). However,
GitHub-hosted runners cannot currently access the NBA official stats/schedule,
and alternate ESPN/CDN endpoints were also blocked. Treat the live system as
NOT OPERATIONAL for NBA predictions until that is resolved.

`NBA_LIVE_ENABLED` is an explicit GitHub Actions variable. Absent or false
disables scheduled live research and daily evidence. It should become true only
after a complete PIT provider end-to-end test is green. Changing the variable
does not install a missing stats provider or guarantee Pinnacle coverage.

Official-provider smoke runs weekly while the route remains blocked.
