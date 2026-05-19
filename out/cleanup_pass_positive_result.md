# Cleanup Pass Positive Result

## Outcome
The cleanup pass produced the first positive ETH-equivalent replay result.

- return: `+4.3094%`
- delta: `+0.0031613924 ETH`
- final side: `BTC`
- trades: `93`
- buys: `47`
- sells: `46`
- rotates: `0`

## Applied logic state
- stronger rotate persistence
- post-rotate hold window
- suppression of weak arm-wait behavior during rotate contexts
- churn guard increased
- rotate signal thresholds raised enough to stop low-quality flip noise

## Interpretation
The first healthy positive logic state does **not** rely on explicit in-position rotates yet.
Instead, the main gain appears to come from:
- cleaner ETH/BTC asset selection from USDC
- reduced interference from weak rotate/reactive churn
- allowing better positions to mature rather than over-trading them

## Important implication
The dedicated rotate-signal work was still useful because it exposed which parts of the stack were destructive.
But the shippable near-term logic may be:
- keep rotate architecture present but conservative
- prioritize positive selection logic first
- only widen rotate behavior later if a tuning matrix proves it improves net accumulation rather than just activity

## Candidate settings used
- `MIN_WETH_ACCUMULATION_PCT=-0.01`
- `REENTRY_SCORE_THRESHOLD=0.08`
- `REENTRY_SCORE_ARM_THRESHOLD=0.03`
- `PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT=0.00`
- `PAIR_ROTATION_COMMIT_PCT=0.02`
- `PAIR_ROTATION_HOLD_BARS=2`
- `PAIR_USDC_EXIT_EDGE_PCT=0.06`
- `PAIR_CHURN_GUARD_BARS=2`
- `ROTATE_SIGNAL_MIN_EDGE_PCT=0.06`
- `ROTATE_SIGNAL_MIN_DEV_PCT=0.03`
- `ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT=0.01`
- `ROTATE_SIGNAL_PERSIST_BARS=2`
- `ROTATE_POST_HOLD_BARS=8`
- `ARM_WAIT_SUPPRESS_DURING_ROTATE=true`
- `ARM_WAIT_MIN_ROTATE_EDGE_PCT=0.18`
- `VOL_MULTIPLIER=0.72`
- `STOP_LOSS=1.30`
- `COOLDOWN_BARS=1`
