# ETH/BTC Rotator 20-Set Tuning Sweep

Script:
- `eth_scalper/scripts/tune_eth_btc_rotator.py`

Objective:
- maximize `eth_equiv_delta_units`

## Result
All 20 tested sets produced the same outcome:
- trades: 0
- rotates: 0
- final ETH-equiv units: 0.0652551461
- delta units: -0.0081044952
- return: -11.0476%

## Top 3 (identical because no set triggered any actions)
1. `r1`
2. `r2`
3. `r3`

## Interpretation
This is a gate-architecture problem, not a simple threshold problem.
The ETH/BTC rotator harness is now present, but its current decision conditions are still too restrictive or internally misaligned for the historical pair replay surface.

## Practical read
Threshold-only tuning cannot produce meaningful rankings until the logic is made action-capable.
The next edits should focus on enabling transitions first:
- convert strict pass/fail entry selection into relative best-opportunity ranking
- allow direct ETH<->BTC rotation when cross-asset edge beats holding edge
- reduce dependency on the old WETH-style reentry arm flow
- add explicit pair-spread / relative-strength triggers so the rotator actually engages
