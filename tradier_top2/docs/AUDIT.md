# Current Tradier Pipeline Audit

## Existing pipeline
Current cron / posting flow:
1. `scripts/post_tradier_tickets.sh`
2. `scripts/tradier_strategy_processor_v2.py`
3. `scripts/tradier_ticket_formatter.py`
4. `scripts/tradier_board_utils.py`
5. board artifact written to `out/tradier_leaders_board.txt`
6. archived via `scripts/tradier_archive_run.py`

## What it currently does well
- Pulls Tradier option chains from a defined symbol list
- Resolves expirations truthfully with fallback labeling
- Filters basic liquidity
- Separates directional/scalping vs premium/credit concepts
- Produces stable board output
- Archives run outputs for later analysis

## What it currently does poorly
- Emits too many leaders
- Ranks mostly on delta/liquidity proximity, not conviction
- Uses hardcoded generic thesis text
- No real market narrative or catalyst framing
- No setup validator tied to underlying structure
- No explicit distinction between “interesting” and “actionable now”
- No top-2 cap for high-conviction review flow
- No calibrated confidence model
- No explicit entry zone / thesis-break logic sourced from actual market context
- No backtest-oriented score decomposition in the rendered output

## Current ranking logic
`tradier_board_utils.py -> score_ticket()` currently favors:
- delta closeness to a target band
- tighter spread ratio
- higher bid
- shorter actual DTE
- exact expiry over fallback

That is useful for contract hygiene, but insufficient for conviction selection.

## Current rendering problem
Board output currently inserts boilerplate:
- “best near-ATM momentum leader in current pass”
- “only on confirmation / momentum continuation”
- generic invalidation / targets / confidence

This makes the board readable, but not trustworthy as a decision engine.

## Artifact review
Latest board confirms the problem:
- multiple directional leaders
- multiple premium leaders
- generic confidence labels
- no symbol-specific narrative
- no clear reason why #1 beats #4 beyond delta/liquidity

## Available historical data
Useful existing artifacts:
- `out/tradier_runs/*/run.json`
- `out/tradier_leaders_board.txt`
- `out/runtime_state/tradier_audit_log.json`

These can seed:
- pick/outcome linkage
- intent history review
- confidence calibration
- false-positive analysis

## Conclusion
The existing Tradier stack is a decent raw candidate generator.
It is **not yet** a top-2 conviction engine.

The next build should preserve the chain fetch/liquidity hygiene layer, then add a new ranking + narrative + validation layer that can output:
- top 2 only
- explicit thesis
- explicit invalidation
- explicit reasons to pass
- confidence with decomposed subscores
- “No Trade” when the field is weak
