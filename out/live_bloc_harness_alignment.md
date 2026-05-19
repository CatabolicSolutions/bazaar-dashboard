# Live Bloc Harness Alignment

## What was fixed
The earlier replay harness was a shortcut proxy and did not mirror the live bot's logic shape.

A new aligned replay harness was created:
- `eth_scalper/scripts/replay_live_bloc_protocol.py`

This harness now mirrors the current live protocol found in `live_main_vps.py`:
- EMA12 / EMA50 adaptive anchors
- adaptive trigger via anchor-distance volatility
- continuation / rollover / armed hold-state logic
- WETH accumulation gate (`weth_accumulation_ok`)
- two-cycle WETH edge scoring
- entry classes: `ideal_dip`, `fair_recovery`, `arm_wait`
- buy/sell/stop decision flow matching the live shape

## Replay result on available dataset
Source used:
- `eth_scalper/out_eth_market_chart_30d.json`

Result:
- rows: 726
- trades: 0
- final side: USDC
- initial WETH-equiv units: 0.0733596413
- final WETH-equiv units: 0.0652551461
- return: -11.0476%

## Interpretation
This does **not** mean the live logic is broken.
It means the currently available historical dataset is too coarse and structurally mismatched for faithful exercise of the live protocol.

Why:
- live logic runs on fast ticks (`CHECK_INTERVAL = 10s`)
- trigger, momentum, reentry, continuation, and rollover logic depend on short-horizon tick behavior
- the local historical file is roughly hourly data, which destroys the exact volatility structure the bot is designed to harvest

## Practical conclusion
The main harness mismatch is fixed.
The next blocker is **data fidelity**, not replay architecture.

To tune the live protocol correctly, the replay input should come from either:
1. real `bloc_trace.jsonl` / fast tick trace from the live bot
2. reconstructed higher-frequency ETH history approximating 10s / 1m movement
3. ideally both, with trace-first validation

## Artifacts
- `eth_scalper/scripts/replay_live_bloc_protocol.py`
- `eth_scalper/out/live_bloc_replay_summary.json`
- `eth_scalper/out/live_bloc_replay_trades.json`
- `eth_scalper/out/live_bloc_replay_trace.json`
