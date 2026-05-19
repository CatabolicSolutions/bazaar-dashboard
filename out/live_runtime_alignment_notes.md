# Live Runtime Alignment Notes

Exact runtime files changed for positive ETH/BTC logic alignment:

- `eth_scalper/config/settings.py`
- `eth_scalper/signals/momentum.py`
- `eth_scalper/bot/main.py`

Harness/analysis-only files NOT required for live runtime:
- `eth_scalper/scripts/replay_live_bloc_protocol.py`
- tuning scripts
- audit scripts
- out/*.json / *.md artifacts

Positive baseline env values to enforce at runtime:
- `BLOC_ROTATE_SIGNAL_MIN_EDGE_PCT=0.06`
- `BLOC_ROTATE_SIGNAL_MIN_DEV_PCT=0.03`
- `BLOC_ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT=0.01`
- `BLOC_ROTATE_SIGNAL_PERSIST_BARS=2`
- `BLOC_ARM_WAIT_SUPPRESS_DURING_ROTATE=true`
- `BLOC_ARM_WAIT_MIN_ROTATE_EDGE_PCT=0.18`

Current limitation from this host:
- local workspace does not expose the actual droplet deploy path
- service file points to `/var/www/bazaar/eth_scalper`, but that path is absent here
- deploy/restart must therefore occur on the droplet target, not assumed locally
