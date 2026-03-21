# Tradier Exit Policy v1

## Purpose
Plumb stop-loss / take-profit / monitoring state into the live Tradier workflow so entry is not the end of the system.

## Core idea
Each open position gets a stored exit policy containing:
- underlying soft stop
- underlying hard stop
- underlying target
- underlying stretch target
- option soft stop
- option hard stop
- option target
- option stretch target
- optional hard-stop auto-exit flag

## Implemented file
- `scripts/tradier_exit_policy.py`

## Current commands
### Set/update policy
```bash
$HOME/.openclaw/workspace/scripts/run_python_script.sh \
  $HOME/.openclaw/workspace/scripts/tradier_exit_policy.py set \
  --position-id IWM-2026-03-20-call-250.0 \
  --trade-type scalp \
  --underlying-soft-stop 250.00 \
  --underlying-hard-stop 249.90 \
  --underlying-target 250.50 \
  --underlying-stretch-target 250.70 \
  --option-soft-stop 1.68 \
  --option-hard-stop 1.60 \
  --option-target 2.05 \
  --option-stretch-target 2.25
```

### Evaluate live state
```bash
$HOME/.openclaw/workspace/scripts/run_python_script.sh \
  $HOME/.openclaw/workspace/scripts/tradier_exit_policy.py eval \
  --position-id IWM-2026-03-20-call-250.0
```

## Current monitor states
- `in_play`
- `warning`
- `target_zone`
- `stretch_zone`
- `exit_now`

## Intended operational use
- `/take` or `/in` creates/opens position
- exit policy is attached immediately
- monitor evaluates policy repeatedly
- state changes drive narrative updates and eventual exit action

## Next hardening step
- auto-wire policy creation from Alfred execution card
- bind state changes to live-position-room alerts
- support `/close` for Alfred-executed exit routing
