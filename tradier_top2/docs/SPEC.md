# Output Spec — Tradier Top-2 Conviction Engine

## Per-candidate fields
- `candidate_id`
- `symbol`
- `direction` (`call` | `put`)
- `setup_class`
- `expiry`
- `requested_dte`
- `actual_dte`
- `fallback_expiry`
- `strike`
- `underlying_price`
- `bid`
- `ask`
- `mid`
- `delta`
- `spread_ratio`
- `confidence_score` (0-10)
- `confidence_components`
  - `underlying_structure`
  - `liquidity_quality`
  - `contract_fit`
  - `narrative_clarity`
  - `validator_strength`
  - `timing_quality`
- `narrative`
- `why_now`
- `what_we_expect`
- `entry_zone`
- `invalidation`
- `targets`
- `risk_notes`
- `reasons_to_pass`
- `review_status` (`candidate` | `watch` | `pass`)

## Run-level fields
- `generated_at`
- `market_context`
  - `vix`
  - `index_regime`
  - `sector_leadership`
- `top_candidates`
- `watchlist_candidates`
- `rejected_candidates`
- `no_trade_reason` (if top_candidates empty)

## Rendering rules
- emit **max 2 top candidates**
- optional short watchlist allowed, but must not dilute top-2 clarity
- every top candidate must include explicit invalidation
- generic boilerplate text is not allowed in final rendering
- if confidence < threshold, candidate does not enter top 2

## Operating rule
If the engine cannot explain:
- why this symbol,
- why this direction,
- why this contract,
- what should happen next,
- and what breaks the thesis,
then it is not ready to emit a trade idea.
