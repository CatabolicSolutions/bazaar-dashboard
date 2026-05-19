# Three-State Rotation Replay Status

## Shipped tonight

### Trusted realized metrics
- Source: `eth_scalper/state/persisted_positions.json`
- Artifact: `out/bloc_trusted_postfix_metrics.json`
- Trusted closed trades found: 1
- Result: -$2.00135, close reason `timeout`

### Historical-only replay harness
- Script: `eth_scalper/scripts/replay_three_state_rotation.py`
- Dataset source: `eth_scalper/out_eth_market_chart_30d.json`
- Output artifacts:
  - `eth_scalper/out/three_state_replay_dataset.json`
  - `eth_scalper/out/three_state_replay_trades.json`
  - `eth_scalper/out/three_state_replay_summary.json`

## Current replay result
Using clean ETH historicals only and the new rotation-style logic:
- rows: 726
- trades: 29
- win rate: 51.72%
- total net P&L: -$2.60184
- total return: -3.20%
- avg hold: 3.24 bars
- exits: 10 hard stops / 14 mean reclaim / 4 timeout / 1 profit retrace

## Read on current logic
The harness is now real and usable, but the strategy is not yet good enough.
Main issue is still payoff shape:
- not enough positive convexity on winners
- too many hard-stop losses
- mean-reclaim exits are harvesting modest gains but not offsetting downside clusters

## Most likely next tuning directions
1. Add stronger regime filter before ETH entry
2. Prevent catching weak falling knives after large local extensions
3. Make profit-taking conditional on stronger peak/retrace structure
4. Extend from ETH-vs-USDC replay into full ETH/BTC/USDC state rotation once BTC historical series is added
