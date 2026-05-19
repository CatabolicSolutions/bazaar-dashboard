# Three-State Rotation - 5 Iteration Tuning

Historical source: `eth_scalper/out_eth_market_chart_30d.json`
Harness: `eth_scalper/scripts/replay_three_state_rotation.py`
Sweep runner: `eth_scalper/scripts/tune_three_state_rotation.py`

## Ranking
1. `v4_patience_bias`
2. `v3_fast_capture`
3. `v2_deeper_discount`
4. `v1_baseline_tighter`
5. `v5_asymmetric_risk`

## Best set: `v4_patience_bias`
Parameters:
- entry_discount_pct: 0.95
- reentry_recover_pct: 0.30
- exit_extension_pct: 0.70
- stop_pct: 0.70
- max_hold_bars: 8
- cooldown_bars: 4

Result:
- trades: 19
- wins: 13
- losses: 6
- win rate: 68.42%
- total net pnl: +$2.37413
- total return: +0.6193%
- avg net pnl / trade: +$0.12495
- avg net pct / trade: +0.08648%
- avg hold bars: 2.84
- exit mix: 4 hard stops / 13 mean reclaim / 1 profit retrace / 1 timeout

## Read
The strongest set was more selective, demanded deeper discount before entry, stronger bounce confirmation, and tolerated a bit more extension before exit. That produced fewer trades, higher win rate, fewer timeout drifts, and the first positive replay result in this pass.
