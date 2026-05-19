# BAZAAR_OPERATING_STATE.md

Canonical operating snapshot for Bazaar of Fortunes.

Use this file to recover active system state quickly across Telegram, Discord, cron, and future sessions.

## Mission
Alfred acts as an execution-focused trading and market-ops copilot for Bazaar of Fortunes.

Priorities:
- precision
- structure
- consistency
- risk-aware ticketing
- operational clarity
- logs for post-trade and end-of-day review

Execution quality outranks verbosity.

## Discord Channel Map
### Tradier / tickets
- `#trading-desk`
- Channel ID: `1483025184775733319`
- Purpose: scheduled leaders-board output / cleaned Tradier tickets

### Tradier / journaling
- `#trading_journal`
- Purpose: factual trade logs and journaling after execution

### Coordination
- `#hq_alfred`
- Purpose: higher-level coordination, not default live-position monitoring room

### Live positions
- Channel ID: `1483580321126416565`
- Purpose: active entered-position monitoring, roadmap, narrative updates, prospective actions, and exit confirmation

## Tradier Current State
### Core pipeline
- `scripts/tradier_strategy_processor_v2.py`
- `scripts/tradier_ticket_formatter.py`
- `scripts/post_tradier_tickets.sh`
- board artifact: `out/tradier_leaders_board.txt`

### Tradier output standard
Normal runs:
- summary-only leaders board
- not raw option-chain dumps
- not debug output
- one post per run

Failure runs:
- raw error
- concise explanation

### Tradier engine status
Implemented:
- truthful DTE labeling
- tighter scalping and credit-spread filters
- liquidity/spread sanity checks
- ranking and capping
- leader representation instead of chain spam
- board presentation layer
- persistent board artifact for downstream delivery

Known note:
- direct Discord posting from a Telegram-bound session is blocked by provider-context policy
- Discord-side session/runtime should own final native Discord delivery


## Live Position Workflow
When a live position is opened:
- use the dedicated live-position room for a short pre-committed roadmap
- roadmap should include:
  - expected path
  - normal discomfort
  - invalidation
  - planned actions if trade works, stalls, or fails
- use `#trading_journal` afterward for factual trade log and lesson capture

## Discord-Native Approval Workflow (Tradier)
Execution should be layered across the existing Discord rooms rather than collapsing everything into one place.

### Flow
1. `#trading-desk` emits leaders / candidates
2. live-position room (`1483580321126416565`) becomes the execution surface
3. Alfred presents an execution card before capital is committed
4. Ross approves explicitly
5. Alfred runs a Tradier order preview
6. Ross commits explicitly
7. Alfred places the order and transitions to monitoring/journaling flow

### Command semantics
Locked-in v1 commands:
- `/take <contract/details>` → final human authorization for Alfred to execute entry
- `/reject <contract/details>` → decline candidate and move on
- `/in ...` → register a manually entered/open/filled position and start monitoring
- `/out ...` → register exit and stop monitoring

### Guardrails
- leaders-board posts are candidates, not automatic entries
- no vague approval language should count as trade authorization
- `/take` is the primary human gate for Alfred-executed entries
- under the hood Alfred should still perform mechanical validation (account state, preview/tradability checks) before placement
- execution should align with scalp philosophy: fast, evidence-based, confirmation-driven, no hope-holding weak setups

## Current Risk / Execution Posture
Tradier:
- disciplined scalp / options workflow
- no hype
- no contradictory tickets
- no fabricated certainty

## Continuity Guidance
If memory search returns weak or empty results, consult this file first.
Then consult:
- `USER.md`
- `memory/2026-03-16.md`
- `memory/2026-03-17.md`

This file is the canonical Bazaar handoff layer.
