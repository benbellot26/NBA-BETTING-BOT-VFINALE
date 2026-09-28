# Pulsar NBA architecture

Pulsar NBA is independent from Pulsar MLB. It borrows governance ideas, not baseball coefficients.

## Production boundary

The V1 model is **research-only** until prospective NBA evidence certifies each market. Market probabilities are never predictive features. The chain is:

`PIT team/player context -> frozen NBA probability model -> probability surface -> executable market -> Pinnacle no-vig benchmark -> uncertainty -> decision gate -> staking`

## Basketball model

The structural projection estimates possessions and points/100 using opponent-adjusted offense/defense, bounded matchup interactions, home/rest/travel/altitude context, and player availability. Regulation rotations must sum to 240 minutes. Missing player minutes are redistributed; absences are not modeled as simply subtracting a player's box-score points.

## Distribution

The first frozen research generation represents margin and total with separate Gaussian safety distributions. This is intentionally simple and auditable. More complex heteroskedastic or possession-level simulations belong in shadow challengers until validated.

## Markets

Supported core markets: Moneyline, Spread and Total. Prices select executable lines and benchmark model output after probabilities have been generated.

## Fail-closed rules

A wager cannot be authorized unless its market is certified, prices are fresh, Pinnacle no-vig is available, uncertainty-adjusted edge clears thresholds, and key lineup uncertainty does not block the decision.

## Research

Sensitivity and ablation tooling is read-only. Any learned coefficients, alternate distributions, referee effects, garbage-time effects or player-impact systems must be promoted explicitly after chronological/OOS and prospective evidence.

## Operational boundary

Synthetic rehearsal, local bundles and JSON snapshots are separate trust domains and cannot authorize paper/live evidence. Live prediction accepts only an OfficialNBAProvider prospective snapshot. Settlement reads final scores through OfficialOutcomeProvider. Operational health and provider availability are observable state, not model features and not betting certification.


## Learned V2 shadow boundary

Software version 1.8.0 keeps `pulsar-nba-v1-structural` frozen as the champion
and adds a separate learned challenger. FINAL prospective forecasts persist a
versioned basketball/context feature vector before settlement. Market-derived
information is stored only under `evaluation_only` for paired scoring.

The learned challenger fits regularized margin and total regressions plus
conditional residual-scale regressions. Evaluation is expanding-window and
point-in-time: a training label must be known before the next test forecast.
V1, V2 and captured Pinnacle no-vig probabilities are compared on paired
holdout games. V2 cannot write paper entries, alter the champion manifest,
change certification, or promote itself. See `V2_RESEARCH.md`.


## Official gamebook alternate-source boundary

NBA Official Scorer's Report gamebooks are an independent official fallback
surface when the JSON stats API is unreachable. They are parsed and aggregated
only into an `ALTERNATE_REFERENCE_ONLY` stat pack. This pack can reproduce
team-level efficiency, pace, style and rotation-minute inputs from completed
games, but it cannot reproduce canonical player on/off OFF_RATING/DEF_RATING
without inventing information.

For that reason, gamebook-derived stats do not automatically satisfy the
production provider contract. They must first pass the explicit
`nba.gamebook_parity` comparison on a matching season/cutoff, then receive
human review and fresh prospective validation under a separately frozen
provider generation. The parity gate never changes betting certification.


### Gamebook reference integrity

The alternate official-gamebook pipeline treats every parsed final box as
content-addressed reference evidence: PDF and parsed-payload checksums are
bound to the Communications schedule identity, and each aggregate stat pack
contains a manifest fingerprint. Parity validates the actual downstream input
contract (all temporal team windows, base FT/3PA rates, season/recent minutes
and advanced usage) before manual review. A passing parity report still cannot
authorize the provider automatically.


### Canonical parity reference capture

Canonical team/player stats used for alternate-source parity are collected by a
separate non-predictive workflow. This decouples parity evidence from injuries,
market data and live-runtime readiness. Failure to reach `stats.nba.com` is
persisted as provider diagnostic state rather than silently selecting the
gamebook source. Exact season/cutoff equality is required before parity runs.


## Postgame outcome authority fallback

Prospective model inputs remain isolated from outcomes. Settlement first asks
the official NBA schedule for final scores. If that transport fails, a
postgame-only adapter can read checksum-validated cached NBA Official Scorer
gamebooks. The evidence audit accepts only `official_nba_schedule` and
`official_nba_gamebook` as outcome sources. Gamebook fallback never modifies
the predictive input manifest or model generation.
