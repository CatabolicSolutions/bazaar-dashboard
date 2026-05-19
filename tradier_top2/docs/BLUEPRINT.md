# Blueprint — Tradier Top-2 Conviction Engine

## Objective
Transform raw Tradier option-chain candidates into at most **two high-conviction review candidates** for manual confirmation and action.

## Layered architecture

### Layer 0 — Raw market intake
Source:
- Tradier quotes
- Tradier expirations
- Tradier option chains
- VIX / index context

Responsibility:
- fetch data reliably
- normalize symbols / expiries / greeks / spreads

### Layer 1 — Hygiene filter
Responsibility:
- liquidity floor
- spread sanity
- DTE bucket fit
- strike sanity
- contract quality pruning

This is mostly what the current processor already does.

### Layer 2 — Underlying opportunity scoring
Responsibility:
Score the **underlying setup**, not just the option contract.

Inputs may include:
- trend alignment
- relative strength vs QQQ/SPY
- reclaim / continuation / breakout context
- volatility state
- event or catalyst context
- extension / chase risk

Output:
- setup class
- long/short directional bias
- narrative summary
- underlying conviction score

### Layer 3 — Contract selection
Responsibility:
For a chosen underlying bias:
- choose best 7DTE or 14DTE contract candidate
- prefer liquid, tradeable, efficient structures
- avoid ugly spread / junk strikes

Output:
- 1 best contract per viable directional thesis

### Layer 4 — Trade framing
Responsibility:
Generate the review card:
- thesis
- entry condition
- invalidation condition
- target framework
- risk notes
- confidence score
- reasons to pass

### Layer 5 — Final selector
Responsibility:
- rank all viable ideas
- emit top 2 max
- emit “No Trade” if nothing clears threshold

## Scoring model (initial)
Confidence score out of 10 built from weighted components:
- underlying structure: 30%
- liquidity / execution quality: 20%
- contract fit: 15%
- narrative clarity: 15%
- confirmation / validator strength: 10%
- anti-chase / timing quality: 10%

## Candidate classes
Initial classes:
- continuation
- pullback reclaim
- breakout retest
- downside continuation put
- event-driven momentum

## Explicit pass conditions
A candidate can be rejected for:
- bad spread
- weak underlying structure
- overextended move
- unclear invalidation
- fallback expiry when exact alternatives are materially better elsewhere
- low narrative clarity
- poor reward-to-risk

## Review workflow
1. Engine emits top 2
2. Conor compares against live chart / tape
3. If setup matches expected behavior, act
4. If invalidated, pass or exit quickly

## Success criteria
The system is working when:
- fewer but better candidates are emitted
- rationale is symbol-specific, not boilerplate
- invalidation is actionable
- “No Trade” happens when deserved
- outcome review can explain why a pick won or failed
