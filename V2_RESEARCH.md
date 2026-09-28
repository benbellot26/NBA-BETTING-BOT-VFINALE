# Learned V2 shadow research

Pulsar NBA 1.8.0 adds a learned challenger around the frozen V1 structural
champion. The champion generation remains `pulsar-nba-v1-structural`.
Nothing in this pipeline authorizes a real wager or changes source-controlled
betting certification.

## Data contract

Every eligible live FINAL forecast captured after this release stores:

- the immutable V1 baseline margin/total and standard deviations;
- a versioned `v2_features` payload built only from pre-tip basketball,
  schedule/context and projected-rotation state;
- `evaluation_only` metadata containing the captured spread/total lines and
  available Pinnacle no-vig HOME/OVER probabilities.

The learned training matrix is created only from `v2_features`. Market lines,
prices, bookmakers, Pinnacle probabilities, sharp edge and betting decisions
are excluded by construction. Forecasts captured before the feature contract
remain valid V1 evidence but are not retroactively reconstructed for learned
V2 training.

## Model

The learned shadow uses deterministic standard-library ridge regressions for:

1. final home-minus-away margin;
2. final game total;
3. log absolute margin error;
4. log absolute total error.

Mean models use standardized basketball/context features. Conditional residual
models convert predicted absolute error to a Gaussian standard deviation via
`sigma = MAE * sqrt(pi/2)`, with conservative floors/ceilings. The variance
labels use an internal chronological holdout when the training sample is large
enough, instead of simply fitting the same residuals used to estimate the mean.

The feature set includes the frozen V1 projection, raw season/30/15/10/5 ORtg-DRtg-Pace windows for both teams, blended team efficiency/pace/style, rest and schedule density, travel/timezone/altitude, and projected rotation impact/availability. The raw windows let the challenger learn temporal weighting instead of inheriting V1's fixed recent-form weights. It does not include any market-derived feature.

## Evaluation

`nba.v2_walkforward` uses expanding chronological folds. Before each test
block, a training row is eligible only when its outcome timestamp is already
known by the first forecast timestamp in that block. This prevents same-day
look-ahead.

V1 and V2 are scored on the exact same holdout games for:

- margin MAE;
- total MAE;
- ML Brier / LogLoss / ECE;
- HOME spread Brier / LogLoss / ECE when the captured line is available;
- OVER total Brier / LogLoss / ECE when the captured line is available.

Captured Pinnacle no-vig probabilities are scored separately as an
`evaluation_only` benchmark. They are never exposed to model fitting.

## Commands

Export replay evidence:

    python -m nba.replay_export

Run the complete learned V2 research chain:

    python -m nba.v2_research

Defaults require 400 enriched training games before the first fold, at least
100 out-of-sample predictions, and a 50-game walk-forward step.

Manual lower-sample research is possible with explicit arguments, for example:

    python -m nba.v2_research --minimum-train 200 --minimum-holdout 100 --step 25

This changes only the research run. The manual-review gate still defaults to
250 paired holdout games unless `--review-holdout` is explicitly changed.

The GitHub Actions workflow **Pulsar NBA V2 Shadow Research** is
`workflow_dispatch` only. It hydrates the immutable `runtime-data` branch,
runs the same pipeline and uploads the resulting research artifacts.

## Promotion boundary

A V2 report is always emitted with:

- `role=SHADOW`;
- `promoted=false`;
- `auto_betting_certification=false`.

The V2 gate can only return `MANUAL_REVIEW_ONLY`. A passing gate means the
challenger is eligible for human code/model review. Promotion would require a
new explicitly frozen generation followed by fresh prospective validation; it
does not inherit V1 evidence or betting certification.
