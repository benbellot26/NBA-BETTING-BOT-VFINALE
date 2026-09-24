# Pulsar NBA runbook

## Repository boundaries

Source code and frozen reference state live on main. Mutable prospective evidence lives on runtime-data. Do not merge runtime-data into main.

## Required secret

ODDS_API_KEY is required by the live research workflow. Store it in GitHub repository Actions secrets. Never commit it to a file.

## Scheduled flow

Pulsar NBA Live Research runs every 20 minutes during the usual NBA game window in UTC. It hydrates the prior runtime-data state, runs the live model, records FINAL paper-eligible candidates, captures a near-close Pinnacle snapshot when available, uploads an artifact, then persists runtime back to runtime-data.

Pulsar NBA Daily Evidence runs once per day. It settles completed paper entries from the official NBA schedule, joins captured closes, refreshes proper scores and CLV diagnostics, and writes a certification candidate.

Pulsar NBA Provider Smoke checks the official schedule, NBA.com team stats and the official injury-report feed once per week.

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

## Offline research on a local computer

`nba.pit_bundle collect` is an optional way to test data access from a
non-GitHub network. It collects official schedule, PIT stats and injury
reports only; it does not need an odds API secret. It requires the target
season to have enough actual statistical history, and a submitted injury
report for both teams. A failure is returned, not simulated data.

    python -m pip install .
    python -m nba.pit_bundle collect --date 2026-11-01 --output nba_local_bundle.json
    python -m nba.pit_bundle analyze --input nba_local_bundle.json --output nba_offline_report.json

For optional line probabilities, supply a JSON object keyed by game ID:

    {"0022600123": {"spread_line": -3.5, "total_line": 226.5}}

and add `--lines lines.json` to the analyze command. An imported bundle
is always unverified research, even if the filename or timestamp looks
official. SHA-256 detects corruption, not authentic collection time.
Never upload a personal Odds API secret in the bundle.

## V1.3 evidence audit and outcome calibration

The prospective chain now preserves a full predictive input SHA-256 manifest
for every eligible FINAL forecast and later qualifying paper entry. Do not
edit these ledgers or substitute corrected post-tip inputs. Source checksums
prove consistency with the stored bytes, not third-party data authenticity.

After the official-score settlement, the daily workflow runs:

    python -m nba.evidence_audit

A failed audit blocks normal runtime-data persistence and leaves an artifact
for diagnosis. Whole-slate calibration is computed independently from paper
selection to avoid hiding model errors by reporting only high-edge picks.
Late historical closes refresh the derived performance view, never rewrite
settlement rows. These changes do not re-enable any scheduled workflow.

## V1.4 provider contract and CI end-to-end test

All new acquisition adapters must return a validated ProviderSnapshot.
The contract enforces season, target date, previous-day statistical cutoff,
timezone-aware timestamps and pre-tip capture. Provider adapters do not gain
permission to certify data merely by implementing the interface.

Run the network-free integration proof with:

    python -m nba.e2e_dryrun

This deterministic fixture is SYNTHETIC_CI_ONLY and is prohibited from the
prospective evidence branch. It is intended to catch integration regressions
while external providers remain unavailable from GitHub-hosted runners.

V2 shadow review readiness is evaluated separately:

    python -m nba.v2_gate --input runtime/research/v2_shadow.json

A review_ready=true result never modifies the champion, never writes a live
certification and never authorizes a wager. Promotion requires explicit source
changes, human review and a fresh prospective validation cycle.

## V1.5 — preseason-only verification

From the repository root run:

    python -m nba.preseason_check --output runtime/preseason_readiness.json

This check calls no websites and does not use ODDS_API_KEY. It validates the
software and static workflow gates only. Keep NBA_LIVE_ENABLED unset/false
until a separate official data-provider smoke and full live paper rehearsal
succeed on the intended runner. Do not count synthetic CI games as evidence.

## V1.6 operating rehearsal

Before enabling scheduled research:

1. Run python -m nba.preseason_check.
2. Run python -m nba.preseason_rehearsal.
3. Run python -m nba.full_rehearsal.
4. When real NBA events are listed by the odds provider, manually dispatch Pulsar NBA Manual Market Smoke with require_events=true.
5. Re-run the official provider smoke on the intended GitHub runner.
6. Only after both real-provider checks pass should NBA_LIVE_ENABLED be considered for paper research.

The live workflow writes runtime/health.json. ANALYSIS_BLOCKED and PROVIDER_DEGRADED states fail the Actions job after artifacts/state are persisted, so GitHub workflow-failure notifications act as the operational alert.

The shared persistence script is idempotent and serialised by the nba-runtime-data concurrency group. It creates runtime-data if absent and converts legacy contents to a data-only branch. Daily artifacts provide an additional retained backup.

The market-smoke workflow is also triggered once by the V1.6 merge because its workflow file is new. Normal future checks remain manual unless the diagnostic code/workflow changes.


### Odds request budget and explicit preseason mode

Paid/current market calls share `runtime/odds_budget.json`. The default daily cap is 48 requests and can be lowered with `NBA_ODDS_DAILY_REQUEST_BUDGET`. A request is reserved before the HTTP call, so failures still count conservatively. `python -m nba.live_runtime --mode preseason` never writes paper entries or FINAL prospective forecasts. Scheduled production research remains `regular`.

## V1.6.1 — odds request budget caveat

NBA_ODDS_DAILY_REQUEST_BUDGET counts outbound requests; The Odds API can charge multiple quota credits per request. The market-smoke response reports provider quota telemetry separately. Inspect the available quota before scheduling repeated market pulls. If runtime/odds_budget.json is corrupt or unreadable, fix or restore it; the bot must not silently reset today's spend.

## V1.6.2 — safe closing snapshots

Closes are timestamped after the Odds API HTTP response. If the response
arrives after tip or the Pinnacle book's quote timestamp is in the future,
before paper entry or after tip, no close is recorded. The market smoke
uses only valid paired Pinnacle contracts on the same NBA event. Its workflow
runs only by explicit manual dispatch; no push-triggered paid checks.

## V1.6.3 — stats cache repair procedure

If the cached stats integrity check fails, preserve the failed runtime
artifact for diagnosis. Do not modify the cached JSON or its SHA manually.
After confirming the required cutoff and source are reachable, obtain a
new official prospective capture before tip. Never backdate a new capture
or treat a local file checksum as independent proof of provider authenticity.


## V1.6.4 — operational readiness

Provider smoke now distinguishes a transport failure from data that simply has not been published yet. Before a real preseason rehearsal, manually refresh provider smoke and market smoke, then run `python -m nba.readiness_gate`. The default gate requires both diagnostics to be no more than 24 hours old. A passing gate is permission to rehearse the data path only; NBA_LIVE_ENABLED remains a separate manual control and source-controlled betting certification remains false.

## V1.6.5 — event matching for closes

New paper entries carry the Odds API event id observed at entry. Closing
capture must find that same provider event id plus the same home/away teams.
Legacy rows without an event id retain the stricter team + exact-tip fallback.
Never edit an event id in a prospective ledger to make a later close match.

## V1.6.6 — alternate trusted data runner

The provider, live-research and daily-evidence workflows read the repository
Actions variable `NBA_DATA_RUNNER`. Leave it unset to use `ubuntu-latest`.
If official NBA endpoints remain blocked from GitHub-hosted runners, the
variable may point to a trusted runner label with working network access.
Never use an untrusted public runner: live research receives ODDS_API_KEY and
writes prospective evidence. Switching runners does not make stale or
post-tip data valid and does not enable NBA_LIVE_ENABLED automatically.

## V1.6.7 — manual preseason rehearsal without live enablement

Use the **Pulsar NBA Live Research** workflow with
`operating_mode=preseason` for a real-source rehearsal while
`NBA_LIVE_ENABLED` remains unset/false. The workflow first refreshes the
official-provider smoke on the selected NBA_DATA_RUNNER, then runs the
preseason runtime. Manual or scheduled `regular` research still requires
`NBA_LIVE_ENABLED=true`. Preseason mode never writes paper/prospective
evidence and never captures a regular close ledger.
