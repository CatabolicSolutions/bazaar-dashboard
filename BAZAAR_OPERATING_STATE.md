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

### Kalshi / prediction-market channel
- Channel ID: `1483308037111283784`
- Purpose: Kalshi review / leaders / recommendation flow
- Plain-text trigger: `/coinflip`

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

## Kalshi Current State
### Core pipeline
- `scripts/kalshi_strategy_processor.py`
- `scripts/post_kalshi_tickets.sh`
- shared runner: `scripts/run_python_script.sh`

### Kalshi trigger semantics
`/coinflip` means:
- run Kalshi review
- produce leaders / recommendation if valid candidates exist
- otherwise output explicit `No Trade`

### Kalshi mission
Prediction markets are intended to become a disciplined 24/7/365 marginal-return engine.

### Kalshi current posture
- auth/runtime works
- selector works
- explicit `No Trade` works
- rejection audit works
- execution-worthy discovery is still under development
- approved next architecture: probability-first Kalshi refactor

### Kalshi preferred market types
Highest priority:
- macro / economic data
- Fed / rates
- CPI / inflation / GDP / unemployment / claims
- index-close / range markets
- corporate-event / earnings markets

### Kalshi setup archetypes
Prioritize:
- mispricing / arbitrage vs legitimate external anchor
- high-probability yield
- event-driven asymmetry

### Kalshi market tolerance
- macro / economic / index close: yes
- corporate events / earnings: yes
- sports: do not categorically reject if a contract is structurally clean and survives pricing/clarity/edge filters
- politics: no by default except rare economically legible binaries
- crypto-event markets: high scrutiny; default no unless edge is unusually clear

### Kalshi output standard
Normal runs:
- summary-quality output only
- concise, operational, disciplined

Failure runs:
- raw error
- concise summary
- obvious next action if known

If no edge exists:
- explicit `No Trade`
- include rejection audit when useful

Never post:
- raw generic open-market dumps
- placeholder spam
- debug noise unless needed for diagnosis

### Kalshi known blocker
The sampled live Kalshi open feed has been dominated by:
- cross-category / combinatoric contracts
- shallow metadata responses that often omit usable tradable quote fields
- contracts too messy to turn into clean Bazaar tickets
- many sports-linked contracts that still fail on structure/clarity rather than category alone

Discovery quality and contract interpretation, not auth/runtime, are the main blockers to execution-worthy Kalshi tickets.

### Kalshi next approved architecture
Probability-first refactor is approved.

Immediate refactor goals:
- move away from quote-first/options-style evaluation
- treat probability as the native language of Kalshi
- separate contract discovery, contract interpretation, fair-probability estimation, edge scoring, and execution validation
- distinguish metadata-only contracts from truly tradable ones
- build `/coinflip` around implied probability vs estimated fair probability rather than raw quote presence alone

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

Kalshi:
- not waiting for mythical perfect conditions
- willing to use practice-grade candidates if structure is clean enough
- moderate sizing acceptable for early live learning
- if still no trade, provide auditable reasons and sample rejected markets

## Continuity Guidance
If memory search returns weak or empty results, consult this file first.
Then consult:
- `USER.md`
- `memory/2026-03-16.md`
- `memory/2026-03-17.md`

This file is the canonical Bazaar handoff layer.
