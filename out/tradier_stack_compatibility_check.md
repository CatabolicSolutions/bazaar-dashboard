# Tradier Stack Compatibility Check

## Verified compatibility areas
### 1. Account connection
- live account connectivity confirmed for account `6YB74771`
- profile, balances, and positions endpoints resolve successfully
- preview path reaches Tradier and returns structured validation responses

### 2. Leaders-board -> approval compatibility
- leaders are archived structurally in `out/tradier_runs/*/run.json`
- approval flow can now select latest archived candidates and prepare preview payloads
- candidate matching improved to handle common contract hint forms such as:
  - `IWM 250C`
  - `IWM 250.0C`
  - `IWM 250 Call`

### 3. Manual entry compatibility
- `/in` parser added for manual position entry
- canonical accepted form:
  - `/in 2 IWM 250C 3/20/26 @ 1.86`
  - `/in 2 IWM 250 Call 3/20/26 @ 1.86`
- parser normalizes to the same position schema used by the monitor

### 4. Manual exit compatibility
- `/out` parser added for exit handling
- canonical accepted form:
  - `/out 2 IWM 250C 3/20/26 @ 1.90`
- closes matching open position and computes simple realized PnL%

### 5. Approval -> /in compatibility
- if a `/in` command matches the active approved candidate, approval metadata is attached to the position record
- this preserves continuity between:
  - leaders-board candidate
  - approval/preview
  - filled position

## Current remaining gaps
### 1. Discord message-trigger automation
- `/approve`, `/commit`, `/reject`, `/in`, and `/out` are implemented as scripts/state transitions
- they are not yet automatically invoked from Discord messages without surface glue

### 2. Journal auto-post on `/out`
- closed positions are now stored structurally
- journal message generation/posting still needs direct automation

### 3. Account-state enforcement before commit
- connection is confirmed
- buying power / uncleared funds checks still need to be enforced as a pre-commit guard

## Compatibility conclusion
The stack is now materially more coherent:
- manual entry path and approved-signal path can converge into one position lifecycle
- naming/contract matching is less brittle
- journaling data capture is structurally possible without losing continuity

## Recommended next enforcement step
Add account-state checks before `commit` so live placement is blocked when:
- option buying power is zero
- funds are uncleared
- account status is not execution-ready
