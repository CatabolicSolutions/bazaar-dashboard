# ETH/BTC Rotator Progress

## What changed
- Built paired ETH/BTC historical input by adding:
  - `eth_scalper/out_btc_market_chart_30d.json`
- Refactored replay toward ETH/BTC rotation architecture in:
  - `eth_scalper/scripts/replay_live_bloc_protocol.py`

## Current harness behavior
The harness now:
- aligns ETH and BTC price series
- computes adaptive EMA/volatility structure across the pair
- scores candidate inventory transitions
- supports BUY / ROTATE / SELL / STOP event classes
- evaluates accumulation in ETH-equivalent units

## Current result
- trades: 0
- rotates: 0
- objective still negative due to idle USDC terminal posture versus ETH benchmark

## Interpretation
This is no longer just a wrong-architecture problem.
Now the harness is on the right surface, but the inherited thresholds / signal conditions are too restrictive for this ETH/BTC historical replay.

## Immediate next tuning direction
Tune the rotator-specific entry and transition gates:
- reduce accumulation gate hardness for cross-asset switches
- loosen reentry-score arming threshold
- change candidate selection from strict pass/fail to relative-best opportunity ranking
- make ROTATE available before falling back to SELL->USDC logic
- tune spread / reversal thresholds specifically for ETH/BTC pair behavior
