# Pulsar NBA — Probability & Decision Engine

Pulsar NBA is a standalone NBA probability, market, research and decision engine. It is independent from the MLB repository and shares governance principles, not baseball coefficients.

## Current status

**V1.6.8 — RESEARCH ONLY.** Software readiness does not imply betting certification. The authoritative source state in `data/nba_betting_certification.json` starts uncertified, and runtime evidence can only produce a certification candidate after the prospective gates are satisfied.

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
- **Pulsar NBA Provider Smoke** — weekly health check of official schedule/stats/injury sources.
- **Pulsar NBA Live Research** — scheduled pregame analysis, paper cohort and live Pinnacle close capture.
- **Pulsar NBA Daily Evidence** — settlement and performance/certification refresh.

## Live hardening and V2 shadow

The live runtime refuses games whose official injury report is NOT YET SUBMITTED,
whose player names do not resolve to the projected rotation (excluding G League
assignments), or whose NBA.com/statistical snapshots or executable odds are stale.
Pinnacle spread pairs use opposite handicaps; totals use an identical number.
Whole-point spread/total contracts remain research-only until push probability
is modeled explicitly. The current basketball champion and real-bet certification
are unchanged.

The Odds API key is tested with an authenticated, low-cost sports-catalog
request by the Odds Key Smoke workflow. It verifies authentication only; current
NBA markets, Pinnacle coverage, available bookmakers and subscription quota
can vary. No key is printed or committed.

Every eligible FINAL game, regardless of whether its candidate qualifies for
paper betting, is archived as an immutable pre-tip forecast. Completed-game
outcomes are joined from the official NBA schedule. The resulting PIT replay
dataset can be used by the independent V2 shadow calibrator:

    python -m nba.replay_export
    python -m nba.v2_shadow --input runtime/research/pit_dataset.jsonl --train-cutoff 2027-01-01T00:00:00Z --holdout-start 2027-01-02T00:00:00Z

The dates above are examples, not a claim that the corpus exists today.
V2 requires at least 400 historical PIT training observations and 100 subsequent
out-of-sample games by default. It only reports paired metrics; it does not
promote itself or authorize real betting.

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

## Current acquisition limitation (September 2026)

The Odds API authentication smoke is green, but official NBA schedule requests
return HTTP 403, NBA stats time out, and the expected official injury PDF
index is not available on GitHub-hosted runners. Independent ESPN/CDN probes
also returned 403. These are production-blocking provider-access failures,
not proof that NBA markets or prediction code are broken.

The scheduled live and daily-evidence jobs are therefore **disabled by default**.
They require an explicit repository Actions variable `NBA_LIVE_ENABLED=true`
after independent provider smoke checks succeed. Keep it disabled until a
reachable, point-in-time-safe NBA stats/injury source is integrated. The Odds
API key alone cannot provide NBA player and team statistical history.

The runtime now **skips paid odds acquisition** whenever the statistics or
official injury data are missing. A failed provider never causes an
uncertified bet. No purchased third-party data subscription is assumed.

## Locally captured PIT research bundle

If official NBA endpoints work from your computer but are blocked from a
GitHub-hosted runner, the new `nba.pit_bundle` tool provides a *manual,
research-only* capture/import path without any second API key. It fetches the
official schedule, season/player inputs and official injury report locally,
then records capture timestamps and a SHA-256 checksum:

    python -m nba.pit_bundle collect --date 2026-11-01 --output nba_local_bundle.json

To run the structural model on that bundle:

    python -m nba.pit_bundle analyze --input nba_local_bundle.json --output nba_offline_report.json

You can optionally provide a JSON map of NBA game IDs to the market's
`spread_line` and `total_line` using `--lines path/to/lines.json`.
All imported files are explicitly **UNVERIFIED_OFFLINE_RESEARCH**: the
checksum catches accidental changes but does not prove when or where a
file was originally created. Offline analysis NEVER adds a paper cohort,
certifies a model or authorizes a real bet. A manual bundle is not a
substitute for independent live provider validation.

## V1.3 — predictive input lineage and unbiased calibration

Each LIVE FINAL forecast records a SHA-256 input manifest binding the exact
team statistics snapshot, official injury PDF snapshot, player rotations,
team strengths, calendar context, model generation and probability policy.
A later paper selection can legitimately use an updated injury snapshot,
but must carry its OWN manifest. The first eligible FINAL forecast is frozen
for the unselected whole-slate evaluation cohort.

`nba.evidence_audit` checks the chain from predictive inputs to forecast,
paper entry, close, official outcome and settlement. It checks timestamp
ordering, incompatible betting contracts and portfolio result arithmetic.
Its result is a research audit, never permission to wager.

Brier, LogLoss and ECE now report an **all-analyzable-games** ML, HOME
spread and OVER total cohort separately from selected paper bets. A push
has no binary label and is excluded from that market's resolved sample.
Certification requires prospective whole-slate calibration in addition
to selected paper/paired-sharp/CLV evidence. Late historical closes are
joined into derived performance without changing the original settlement.

The project is still **not live-operational** on GitHub-hosted runners:
official NBA stats/schedule/injuries failed independent provider checks.
The `NBA_LIVE_ENABLED` repository variable must remain unset/false.

## V1.4 — provider contract and deterministic end-to-end proof

Acquisition now has a stable DataProvider boundary. OfficialNBAProvider uses
the current official schedule/stats/injury adapters; BundleProvider loads an
explicitly unverified local research bundle; JsonSnapshotProvider accepts
schema-compatible research snapshots. The predictive model no longer needs
a provider-specific object shape.

CI also runs `python -m nba.e2e_dryrun`. This network-free fixture traverses
team inputs, rotations, context, structural projection, probability surfaces,
Pinnacle-style market pairing, uncertainty, decisions and predictive lineage.
It must produce six market candidates and zero BETs because the fixture is
uncertified. This is software evidence only; synthetic inputs never enter the
prospective performance ledger.

V2 shadow output can be checked with:

    python -m nba.v2_gate --input runtime/research/v2_shadow.json

The V2 review gate requires at least 250 paired holdout games by default,
forbids material degradation in Brier/LogLoss/ECE/margin MAE/total MAE and
requires at least two strict metric improvements. A passing report only says
MANUAL_REVIEW_ONLY; auto_promote and betting_certified remain false.
A human-reviewed frozen model generation would still need new prospective
validation before any live approval.

## V1.5 — official provider integration and preseason check

The live runtime now uses OfficialNBAProvider.capture() and validates its
ProviderSnapshot before any odds request. No scheduled games, blocked
statistics, unsubmitted official injuries and stale input timestamps prevent
paid odds acquisition. Earlier games already underway no longer block later
upcoming games on the same NBA date.

JsonSnapshotProvider and BundleProvider remain unverified offline research
inputs; neither can impersonate the official live source. All betting gates
remain uncertified and NBA_LIVE_ENABLED is not enabled by this release.

For preseason development run the strictly network-free command:

    python -m nba.preseason_check

It checks imports, the deterministic six-market end-to-end fixture, locked
source-controlled certification and the static live-workflow guards. A green
software check is not proof of upstream provider availability. The report
explicitly says live_operational=false and odds_api_requests=0.

## V1.6 — preseason operations

V1.6 prepares the operating layer without pretending that future NBA evidence already exists. It adds provider-specific HTTP headers, an outcome-provider adapter for settlement, two synthetic rehearsals, persistent health reporting, a workflow alert gate, manual NBA/Pinnacle market diagnostics with quota telemetry, exact-entry-line preference for closing CLV, DST coverage tests, and crash-safe runtime-data persistence.

Useful commands:

    python -m nba.preseason_rehearsal
    python -m nba.full_rehearsal
    python -m nba.health_report
    python -m nba.market_smoke

The market smoke is manual because it consumes one Odds API request. Synthetic rehearsals are never prospective evidence. V1.6 also persists a UTC daily Odds API request budget (default 48, configurable with NBA_ODDS_DAILY_REQUEST_BUDGET); analysis, close capture and market diagnostics fail closed when that budget is exhausted. `live_runtime --mode preseason` can exercise real plumbing while refusing to write paper or FINAL prospective evidence.

The first V1.6 merge to `main` also runs the market diagnostic once automatically. It consumes one Odds API request, does not require events to exist, and never certifies betting.

## V1.6.1 — early-season spend protection

Regular-season research checks both teams' five-completed-game minimum **before** reserving or requesting paid odds. If every upcoming game fails the sample gate, it records NO_ANALYSIS and spends zero odds requests. Preseason plumbing still uses its explicit research-only mode. The persistent daily budget is a cap on HTTP requests, **not** a cap on provider credits: one request may cost multiple credits depending on markets and plan. A corrupt budget ledger now fails closed rather than silently resetting to zero.

## V1.6.2 — PIT close integrity and market pairing

Live Pinnacle closes now record HTTP response-receipt time, never the
request start. Close evidence is rejected when the response arrives at/after
tip or the quote timestamp is outside the original entry-to-pre-tip window.
The NBA market diagnostic now requires valid paired Pinnacle ML, Spread and
Total contracts **on the same event**; other bookmakers cannot falsely make
Pinnacle coverage appear ready. It is manual-only to avoid unrequested paid
API calls on a routine code merge.

## V1.6.3 — persisted stats/cache integrity

Each cached NBA statistics pack is validated against its canonical content
SHA-256, cutoff/season, capture metadata, and original snapshot file before
the model can read it. A missing or modified original snapshot fails closed
rather than silently rebuilding the evidence or reusing stale metadata.
Integer advanced-window keys are normalized after JSON reload so canonical
digests remain consistent. These hashes detect local inconsistency; they do
not independently prove upstream provider authenticity or publication time.

## V1.6.4 — freshness-aware operational readiness

Provider smoke now reports explicit states such as READY, BLOCKED and WAITING_FOR_PUBLICATION, with per-source states including ACCESS_BLOCKED, TIMEOUT, NOT_PUBLISHED and HISTORICAL_ONLY. A previous-season stats/injury probe can demonstrate transport/parser health but can never make current-season acquisition operational. The offline `nba.readiness_gate` requires recent provider and paired-Pinnacle diagnostics before declaring the system ready for a real rehearsal. It never enables live workflows or betting.

## V1.6.5 — Odds event execution lineage

The Odds API event identifier is now preserved from the matched pregame market
into paper-entry and closing-price evidence. Close capture prefers this stable
provider event id and refuses to fall back to a same-team/time match when an
expected id disappears. The id is execution metadata only: it is deliberately
excluded from the predictive input manifest and model features.

## V1.6.6 — portable NBA data runner

The official-NBA provider, live-research and daily-settlement workflows now use
`NBA_DATA_RUNNER` when configured and otherwise fall back to
`ubuntu-latest`. This gives the acquisition layer a clean migration path to a
trusted runner/network if GitHub-hosted egress remains blocked. Only use a
trusted runner because live research can receive repository secrets. Changing
the runner does not bypass PIT checks, certification gates or provider
validation. An HTTP 404 from the season-specific official injury page is now
classified as NOT_PUBLISHED rather than a generic transport outage.

## V1.6.7 — safe manual preseason dispatch

A manual GitHub Actions dispatch can now run `operating_mode=preseason`
without setting `NBA_LIVE_ENABLED=true`. Scheduled jobs and manual
`regular` research remain locked behind that variable. The preseason path
runs a fresh official-provider smoke first and still cannot write paper entries
or FINAL prospective forecasts. This allows real plumbing rehearsal without
opening the regular-season automation gate.

## V1.6.8 — operational watch and diagnostic refresh

Official-provider health is checked daily without using Odds API credits.
The same workflow also writes a network-only runner probe covering the
existing CDN route, NBA API Hub schedule page, NBA Communications schedule
release, official injury page and a historical stats API request. These probes
are diagnostic only and can never become predictive evidence.

Provider and market diagnostics now automatically refresh the persisted
readiness and health snapshots. Readiness rejects legacy diagnostic schemas so
an old green-looking report cannot satisfy the current gate. This release also
contains a one-time push marker that refreshes the current V2 Pinnacle market
diagnostic after merge; normal future market checks remain manual.
