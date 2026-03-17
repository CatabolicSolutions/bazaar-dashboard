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
- sports/cross-category combinatoric contracts
- markets without usable price reference
- contracts too messy to turn into clean Bazaar tickets

Discovery quality, not auth/runtime, is the main blocker to execution-worthy Kalshi tickets.

## Live Position Workflow
When a live position is opened:
- use the dedicated live-position room for a short pre-committed roadmap
- roadmap should include:
  - expected path
  - normal discomfort
  - invalidation
  - planned actions if trade works, stalls, or fails
- use `#trading_journal` afterward for factual trade log and lesson capture

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
