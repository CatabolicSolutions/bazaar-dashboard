# Discord Native Trade Approval v1

## Objective
Insert controlled trade actualization into the existing Bazaar Discord workflow without breaking the current channel separation.

## Channel Roles
### 1) Trade candidate source
- `#trading-desk`
- Channel ID: `1483025184775733319`
- Role: scheduled leaders-board output and candidate discovery only

### 2) Live execution / active management
- Live position room
- Channel ID: `1483580321126416565`
- Role: approval, entry confirmation, roadmap, monitoring, and exit updates

### 3) Rules / operating standard
- Rules channel / pinned workflow reference
- Channel ID: `1483517457049325892`
- Role: durable operating procedure / execution rules / approval semantics

## Core Principle
No live trade should be actualized directly from a leaders-board post alone.
The leaders-board is a candidate generator.
The live-position room is where a candidate becomes an approved trade.

## Proposed Native Workflow
### Step 1 — Candidate appears
A scheduled Tradier leaders-board post lands in `#trading-desk`.

### Step 2 — Candidate is escalated
Either Alfred or Ross references the candidate in the live-position room.
This creates a separation between:
- idea generation
- execution intent

### Step 3 — Alfred produces an execution card
Before any trade is green-lit, Alfred should produce a compact execution card in the live-position room containing:
- symbol
- contract
- thesis
- trigger / confirmation condition
- target zone
- stop / invalidation
- confidence / posture
- whether the setup fits scalp philosophy

### Step 4 — Explicit approval command
Approval should be explicit and unambiguous.
Recommended approval syntax:
- `/approve <symbol/contract>`
- optional later: `/approve top` when only one live candidate is under discussion

No execution should happen from vague phrases like:
- "looks good"
- "send it"
- "maybe take it"

### Step 5 — Order preview
After approval, Alfred prepares an order preview using Tradier preview mode.
Preview response should surface in the live-position room with:
- side
- qty
- limit price / order type
- estimated cost
- order validity / preview result

### Step 6 — Final commit
Recommended final commit syntax:
- `/commit`

At this stage:
- Alfred places the order
- Alfred confirms order id / state
- Alfred transitions to active monitoring

### Step 7 — Native position lifecycle
Once filled, normal live-position workflow takes over:
- `/in ...` if manual entry confirmation is still needed
- roadmap narrative
- monitoring updates
- `/out ...` on exit
- journal handoff

## Immediate Consensus Recommendation
### What gets green-lit
Only candidates that satisfy all of the following:
- clean underlying structure
- tradable liquidity / spread profile
- coherent scalp thesis
- identifiable invalidation
- appropriate time window
- no major macro/event conflict without explicit acknowledgment

### What should not get green-lit
- fallback-expiry candidates unless explicitly accepted
- low-liquidity or wide-spread junk
- trades with no clear invalidation
- tickets that conflict with the daily macro overlay
- setups that require wishful thinking rather than confirmation

## Alignment with Scalp Philosophy / Capital Expansion
### Scalp philosophy
- fast, purposeful, evidence-based
- no converting weak scalps into hope holds
- green is acceptable when expansion does not become authoritative
- thesis must pay quickly or risk tolerance tightens

### Capital expansion logic
The system should expand capital by:
- repeating high-quality, high-information setups
- reducing emotional execution variance
- standardizing approval, entry, monitoring, and review
- filtering out low-quality leaderboard noise before capital is committed

Capital expansion should come from repeatability and discipline, not aggression for its own sake.

## v1 Recommended Commands
### Approval layer
- `/approve <contract>` → authorize Alfred to prepare order preview
- `/commit` → authorize live placement after preview
- `/reject` → decline candidate and move on

### Position layer
- `/in ...` → register filled/open position and begin monitoring
- `/out ...` → register exit and stop monitoring

## Why this structure is correct
- `#trading-desk` stays clean and signal-focused
- live-position room becomes the execution surface
- rules channel holds durable policy
- approvals are explicit
- order preview introduces friction in the right place
- capital gets committed only after thesis + structure + risk alignment

## Recommended next implementation order
1. codify approval semantics in rules/pins
2. add Discord-native approval message format
3. connect approval -> Tradier preview
4. connect commit -> Tradier live placement
5. connect fill -> monitoring / journal pipeline
