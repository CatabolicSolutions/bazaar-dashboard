# Tradier Top-2 Conviction Engine

Purpose: replace broad leaderboard spam with a disciplined, reviewable **top-2 short-DTE opportunity engine**.

## Mission
Produce at most **two** option candidates per cycle:
- 7DTE / 14DTE focused
- strong underlying + clear narrative
- liquid contract selection
- explicit entry / invalidation / targets
- confidence score with explainable components

This engine is for **decision support**, not blind execution.
Conor reviews market structure, confirms the setup, then acts if the trade matches the expected behavior.

## Design principles
- Quality over quantity
- Explainable scoring over opaque ranking
- Git-tracked logic, specs, weights, and outcomes
- Backtest and outcome review drive tuning
- “No Trade” is a valid result

## Core outputs
Each candidate should include:
- symbol
- direction
- expiry / DTE bucket
- contract
- setup class
- market narrative
- validators passed / failed
- entry zone
- invalidation level / thesis break
- target framework
- confidence score
- reasons to pass

## Planned components
- `docs/AUDIT.md` — current pipeline audit
- `docs/BLUEPRINT.md` — architecture and scoring blueprint
- `docs/SPEC.md` — field-level output spec
- `config/universe.json` — focused ticker universe
- `config/scoring_weights.json` — explainable scoring weights
- `analysis/top2_engine.py` — conviction ranking layer
- `analysis/setup_validator.py` — setup / narrative validation
- `analysis/contract_selector.py` — 7DTE/14DTE contract selection
- `backtests/` — replay + score calibration scripts
- `out/` — top-2 output artifacts

## Initial scope
Focus first on:
- NVDA
- QQQ
- SPY
- AMD
- META
- TSLA

Expiration focus:
- 7DTE
- 14DTE

## Current truth
The existing Tradier pipeline is still mostly:
- delta/liquidity filtering
- broad leader emission
- generic thesis text

The new engine will sit on top of that path and convert raw candidates into a conviction-ranked review queue.
