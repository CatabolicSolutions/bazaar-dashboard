# Discord Native Trade Approval — Implementation Notes

## Implemented script
- `scripts/tradier_approval_flow.py`

## What it does
- reads the latest archived Tradier leaders run
- selects a candidate from the latest leaders
- emits an execution-card-ready summary (`card`)
- handles explicit approval state (`approve`)
- runs Tradier preview on approval
- stores the active candidate/preview payload in state
- handles explicit commit (`commit`) for live placement
- handles explicit reject (`reject`)
- exposes workflow state (`status`)

## State file
- `out/tradier_approval_state.json`

## Command model
### Build execution card from latest leaders
```bash
$HOME/.openclaw/workspace/scripts/run_python_script.sh \
  $HOME/.openclaw/workspace/scripts/tradier_approval_flow.py card \
  --contract "IWM 250C"
```

### Approval → preview
```bash
$HOME/.openclaw/workspace/scripts/run_python_script.sh \
  $HOME/.openclaw/workspace/scripts/tradier_approval_flow.py approve \
  --contract "IWM 250C" \
  --qty 1 \
  --order-type limit
```

### Commit live placement
```bash
$HOME/.openclaw/workspace/scripts/run_python_script.sh \
  $HOME/.openclaw/workspace/scripts/tradier_approval_flow.py commit
```

### Reject
```bash
$HOME/.openclaw/workspace/scripts/run_python_script.sh \
  $HOME/.openclaw/workspace/scripts/tradier_approval_flow.py reject \
  --reason "macro conflict"
```

## What still needs wiring
- message-surface parser so `/approve`, `/commit`, and `/reject` in Discord invoke these scripts automatically
- account/buying-power checks before preview/commit
- preview formatting/posting back into the live position room automatically
- fill detection -> `/in` handoff
- rejection logging into journal/review layer

## Current value
Even before full message-trigger automation, the approval logic is now formalized and executable:
- candidate -> execution card
- approval -> preview
- commit -> live placement
- reject -> clear state
