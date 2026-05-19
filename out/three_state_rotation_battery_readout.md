# Accumulation-First Battery Readout

Objective: maximize `eth_equiv_delta_units` / `eth_equiv_return_pct`, not USD P&L.

## Sweep
- cases tested: 648
- script: `eth_scalper/scripts/battery_tune_three_state_rotation.py`
- harness: `eth_scalper/scripts/replay_three_state_rotation.py`
- source: `eth_scalper/out_eth_market_chart_30d.json`

## Core finding
The current ETH/USDC volatility-rotation logic is still structurally negative on the accumulation objective.

Even the best battery case ended with fewer ETH-equivalent units than the initial posture.
That means the current logic can produce positive USD P&L while still failing the actual mission.

## Best case found (still negative on objective)
Parameters:
- entry_discount_pct: 0.55
- reentry_recover_pct: 0.30
- exit_extension_pct: 0.40
- stop_pct: 0.75
- max_hold_bars: 4
- cooldown_bars: 2

Outcome:
- initial ETH-equivalent units: 0.0733596413
- final ETH-equivalent units: 0.0670677173
- delta units: -0.0062919240
- ETH-equivalent return: -8.5768%
- trades: 27
- win rate: 66.67%
- USD P&L: +6.26357

## Highest-impact dials (r-like spread on mean unit delta)
1. `REENTRY_RECOVER_PCT`
2. `MAX_HOLD_BARS`
3. `STOP_PCT`
4. `ENTRY_DISCOUNT_PCT`
5. `COOLDOWN_BARS`
6. `EXIT_EXTENSION_PCT`

## Best-value direction by dial
- reentry_recover_pct -> `0.30`
- max_hold_bars -> `4`
- stop_pct -> `0.75`
- entry_discount_pct -> `0.95` by average effect, though best single case used `0.55`
- cooldown_bars -> `2`
- exit_extension_pct -> weak effect in this battery

## Interpretation
The main problem is not fine-tuning exits. The main problem is that this ETH/USDC loop sells away inventory too readily relative to the accumulation objective.

This suggests the next strategy shape should likely:
- anchor to inventory retention first
- only de-risk partial size on high-confidence local extension
- require a much stronger reclaim discount before re-entry
- or move to true multi-asset rotation where exiting ETH can still preserve crypto inventory via BTC instead of collapsing to USDC too often
