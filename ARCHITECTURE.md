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
