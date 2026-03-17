# Position Monitor v1

## Goal
Reduce screenshot-based monitoring by letting Alfred poll a live underlying quote plus exact option contract state from Tradier.

## Current capabilities
- Register an open position with:
  - symbol
  - expiry
  - strike
  - option type
  - entry price
  - quantity
  - optional underlying soft stop / hard stop / target
- Fetch a live snapshot of:
  - underlying last / bid / ask
  - option bid / ask / last / mid
  - delta / volume / open interest
  - rough PnL vs entry using option mid
- Watch the position for repeated polling on a fixed interval

## Current storage
- `out/tradier_positions.json`

## CLI usage
```bash
$HOME/.openclaw/workspace/scripts/run_python_script.sh \
  $HOME/.openclaw/workspace/scripts/tradier_position_monitor.py add \
  --id iwm-250c-2026-03-18 \
  --symbol IWM \
  --expiration 2026-03-18 \
  --option-type call \
  --strike 250 \
  --entry 1.86 \
  --qty 2 \
  --underlying-soft-stop 250.00 \
  --underlying-hard-stop 249.90 \
  --underlying-target 250.50
```

Snapshot:
```bash
$HOME/.openclaw/workspace/scripts/run_python_script.sh \
  $HOME/.openclaw/workspace/scripts/tradier_position_monitor.py snapshot \
  --id iwm-250c-2026-03-18
```

Watch:
```bash
$HOME/.openclaw/workspace/scripts/run_python_script.sh \
  $HOME/.openclaw/workspace/scripts/tradier_position_monitor.py watch \
  --id iwm-250c-2026-03-18 \
  --interval 30 \
  --iterations 10
```

## Next upgrades
- optional Discord alert output
- auto-close / journal handoff
- target/stop alert throttling
- archive snapshots for trade review
- derive option contract symbol if needed for direct quote endpoint
