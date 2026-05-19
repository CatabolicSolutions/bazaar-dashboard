# ETH/BTC Rotator Next Pass

## Goal
Push the harness from active-but-lossy into true in-position ETH<->BTC rotation with lower churn and better ETH-equivalent accumulation.

## What changed
- Added relative-strength entry filtering.
- Added rotation-commit gate intended to prefer ETH<->BTC switches over USDC exits.
- Added churn guard and explicit USDC-exit suppression conditions.

## Immediate result
The first strict rotation-first version overconstrained the machine and returned to zero trades.

## Recovery sweep
A follow-up loosened sweep (`tune_eth_btc_rotator_v3.py`) found one active set again:

### Best set in this pass: `r7`
- return: `-5.4226%`
- delta: `-0.0039780056 ETH`
- trades: `87`
- rotates: `0`

Params:
- `MIN_WETH_ACCUMULATION_PCT = -0.01`
- `REENTRY_SCORE_THRESHOLD = 0.08`
- `REENTRY_SCORE_ARM_THRESHOLD = 0.03`
- `PAIR_SPREAD_TRIGGER_PCT = 0.08`
- `PAIR_REVERSAL_TRIGGER_PCT = 0.03`
- `PAIR_ROTATE_MIN_EDGE_PCT = -0.005`
- `PAIR_ROTATE_EXIT_EDGE_PCT = 0.001`
- `PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT = 0.00`
- `PAIR_ROTATION_COMMIT_PCT = 0.0`
- `PAIR_ROTATION_HOLD_BARS = 1`
- `PAIR_USDC_EXIT_EDGE_PCT = 0.03`
- `PAIR_CHURN_GUARD_BARS = 1`
- `VOL_MULTIPLIER = 0.72`
- `STOP_LOSS = 1.30`
- `COOLDOWN_BARS = 1`

## Interpretation
- We improved from `-5.81%` to `-5.42%`.
- But **rotate_count is still 0**, so the main blocker is now explicit:
  the current rotate/exit logic is not yielding a state where ETH->BTC or BTC->ETH in-position switching wins over the sell-to-USDC path.

## Likely root cause
Candidate edge is still too fee-shaped / symmetric for the held-vs-alt comparison, so the system keeps resolving into entry/exit churn instead of true cross-asset rotation.

## Next concrete move
The next pass should stop treating rotation as a derivative of sell logic and instead:
1. score held asset vs alternate asset directly from spread regime,
2. generate a dedicated rotate signal independent of USDC exit conditions,
3. track counterfactual held-vs-rotated outcome over N bars,
4. only keep rotate rules that outperform hold in ETH-equivalent terms.
