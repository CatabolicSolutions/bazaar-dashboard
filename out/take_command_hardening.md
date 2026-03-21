# /take Command Hardening

## Implemented
`/take` now has a concrete execution path inside `scripts/tradier_approval_flow.py`.

## Behavior
- resolves candidate from latest archived leaders
- builds preview payload
- runs Tradier preview
- snapshots account readiness
- if account is not execution-ready:
  - stores active candidate state
  - marks request as `blocked`
  - records blocker reason
  - does **not** place live order
- if account is execution-ready:
  - places live order immediately after successful preview path
  - stores commit response

## Current interpretation
- `/take` is the primary human authorization command
- account-state validation remains an under-the-hood mechanical gate
- this preserves the intended model:
  - Ross decides whether to take the trade
  - Alfred decides whether the account/order path can support it cleanly

## Remaining gap
- Discord message-surface glue still needs to invoke the script automatically from room messages
- the engine path is now real; the chat binding is the remaining bridge
