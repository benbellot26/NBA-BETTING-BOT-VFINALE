# Pulsar NBA preseason readiness

Updated for V1.6.9 on 24 September 2026.

## Implemented now

- Stable official/input provider boundary.
- Official outcome provider boundary for settlement.
- Provider-specific HTTP headers with no NBA Origin leakage to third parties.
- Network-free preseason readiness check.
- Synthetic preseason rehearsal.
- Full synthetic evening rehearsal: analysis -> market pairing -> close -> settlement -> persistence.
- Runtime-data hydrate/persist scripts with first-run bootstrap and data-only conversion.
- Serialised runtime workflows and retained Actions artifacts.
- Health report and workflow failure alert gate.
- Freshness-aware provider/market readiness gate with no network calls.
- Provider states distinguish access blocks, timeouts, unpublished reports and historical-only stats.
- Official-data workflows support a configurable trusted runner via NBA_DATA_RUNNER.
- Manual preseason workflow dispatch is allowed while regular live automation stays disabled.
- Daily no-credit provider monitoring and a network-only runner route probe are persisted.
- Provider/market runs refresh readiness and health snapshots automatically.
- NBA Communications schedule PDF is used as REFERENCE_ONLY fallback diagnostics.
- One-shot bookmaker discovery records current market coverage without changing Pinnacle.
- DST coverage test for the broad NBA Actions window.
- One-request NBA/Pinnacle market coverage and quota diagnostic.
- Exact entry-contract preference for closing-price CLV.
- Prospective lineage/evidence audit, full-game calibration, paper settlement and V2 shadow/manual-review gates.
- Live and daily workflows remain gated by NBA_LIVE_ENABLED.
- Source-controlled betting certification remains false.

## Must wait for real future data

These are not coding TODOs and cannot be manufactured before the games/data exist:

1. Verify official schedule/stats/injury endpoints on the intended runner when preseason feeds are live.
2. Verify current NBA ML/spread/total and Pinnacle coverage when events are published.
3. Run a real pregame paper rehearsal against an actual upcoming game.
4. Accumulate genuine pre-tip forecasts, closes and independently observed outcomes.
5. Evaluate calibration/CLV/paper performance on that prospective corpus.
6. Train/evaluate V2 only after the required chronological sample exists.
7. Consider any real-betting certification only after the configured evidence gates are satisfied and manually reviewed.

Synthetic fixtures, manually imported bundles and data downloaded after games do not count toward these gates.


## Operational readiness gate

After manually refreshing both the official-provider smoke and the Pinnacle market smoke, run:

    python -m nba.readiness_gate

A pass only means the persisted diagnostics are recent and show the inputs needed for a real preseason rehearsal. It never sets NBA_LIVE_ENABLED, never certifies a market and never authorizes betting.
