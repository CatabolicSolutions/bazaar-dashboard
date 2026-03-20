# Tradier Execution v1 Foundation

## Purpose
Create the first real execution layer beneath the Tradier leaders-board so Alfred can move from analysis/monitoring toward controlled authorized order routing.

## Current scope
Options-only.

## Environment required
- `TRADIER_API_KEY`
- `TRADIER_ACCOUNT_ID` (or `TRADIER_LIVE_ACCOUNT_ID`)
- optional `TRADIER_BASE_URL`
  - live default: `https://api.tradier.com/v1`
  - sandbox example: `https://sandbox.tradier.com/v1`

## Implemented commands
### Preview a single-leg option order
```bash
$HOME/.openclaw/workspace/scripts/run_python_script.sh \
  $HOME/.openclaw/workspace/scripts/tradier_execution.py preview-option \
  --symbol IWM \
  --expiry 2026-03-20 \
  --option-type call \
  --strike 250 \
  --qty 1 \
  --side buy_to_open \
  --order-type limit \
  --price 1.85
```

### Place a live single-leg option order
```bash
$HOME/.openclaw/workspace/scripts/run_python_script.sh \
  $HOME/.openclaw/workspace/scripts/tradier_execution.py place-option \
  --symbol IWM \
  --expiry 2026-03-20 \
  --option-type call \
  --strike 250 \
  --qty 1 \
  --side buy_to_open \
  --order-type limit \
  --price 1.85 \
  --yes
```

### Check status
```bash
$HOME/.openclaw/workspace/scripts/run_python_script.sh \
  $HOME/.openclaw/workspace/scripts/tradier_execution.py status \
  --order-id 123456789
```

### Cancel
```bash
$HOME/.openclaw/workspace/scripts/run_python_script.sh \
  $HOME/.openclaw/workspace/scripts/tradier_execution.py cancel \
  --order-id 123456789 \
  --yes
```

## Safety posture
- preview-first workflow is the default
- live placement requires `--yes`
- cancel requires `--yes`
- all requests/responses are written to:
  - `out/tradier_execution_audit.jsonl`

## What this does not yet do
- account buying-power checks
- position reconciliation / flatten helpers
- multi-leg spread entry
- Discord-native `/approve` execution flow
- execution throttles / daily limits
- automatic kill-switch behavior

## Recommended next layer
1. add account/balances/positions fetch
2. add execution policy file (`max_qty`, symbols, allowed windows)
3. add Discord approval flow
4. add order-state monitor + journal handoff
