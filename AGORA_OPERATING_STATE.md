# AGORA OPERATING STATE

Canonical system snapshot for Agora Algorithm — the connected **asset-management and financial-management** operating surface.

## Identity
- **System name:** Agora Algorithm
- **Scope:** Connected portfolio operations across Tradier, Bloc/BTC, and supporting signal/risk feeds
- **Role:** Asset-management and financial-management operating system
- **Operator:** Alfred
- **Operator role:** Execution-focused trading and market-ops copilot (digital butler)

## Division Architecture

```
AGORA ALGORITHM  (Tradier only)
│
├── Agora Alpha   — Master Edge & Strategy (signal engine)
│     Inputs: market data, Beta regime context, Gamma tuning params
│     Outputs: ranked candidates → Delta; declined runs → Theta
│     Pipeline: strategy processors, edge filters, liquidity/sanity checks
│
├── Agora Beta    — Market Exposure & Regime Context (macro layer)
│     Inputs: macro data, economic calendar, market structure
│     Outputs: regime labels → Alpha, macro context → Thesis, constraints → Delta
│
├── Agora Delta   — Position & Direction Control (construction & sizing)
│     Inputs: Alpha candidates, Beta constraints
│     Outputs: executions → Ledger; declined → Theta; live positions → Thesis
│
├── Agora Gamma   — Risk Acceleration & Adjustment Engine (tuning)
│     Inputs: Ledger performance, Theta declined-run data
│     Outputs: tuning recommendations → Alpha; quantitative support → Thesis
│
├── Agora Theta   — Time, Decay & Lifestyle Management (committed + declined)
│     Inputs: declined/rejected runs from Alpha & Delta
│     Outputs: what-if data → Gamma; decision records → Thesis & Ledger
│
├── Agora Thesis  — Data & Narrative Compilation (conviction storyboard)
│     Inputs: Beta macro, Delta positions, Theta decisions, Gamma insights
│     Outputs: pre/post-position narratives → monitoring room → human
│
└── Agora Ledger  — Ledger (tracking, logs, performance)
      Inputs: Delta executions, Theta decision records
      Outputs: performance data → Gamma; summary data → Thesis
```

## Scope
**Agora Algorithm is now the cross-connection asset manager.**
- Tradier remains the listed-equities/options execution and monitoring connection.
- Bloc / Uniswap rotator remains its own execution runtime, but Agora owns the portfolio-level visibility, allocation, risk, and ledger presentation for it.
- Kalshi remains separate unless explicitly connected later.
- The seven Agora divisions still exist, but the operating surface is now portfolio-first: NAV, liquidity, exposure, risk, candidates, execution gates, and audit trail.

## Script-to-Division Mapping (Tradier only)

```
Agora Alpha:
  - scripts/tradier_strategy_processor_v2.py    — Strategy filters & ranking
  - scripts/tradier_board_utils.py               — Board construction & formatting

Agora Beta:
  - (macro context feeds in but dedicated Beta analysis script pending)

Agora Delta:
  - scripts/tradier_approval_flow.py            — Approval/preview workflow
  - scripts/tradier_auto_trade.py               — Auto-execution logic
  - scripts/tradier_autonomous_trader.py        — Autonomous trading engine
  - scripts/tradier_cli_interaction_model.py    — CLI interaction model

Agora Gamma:
  - (emerging — will draw tuning data from Ledger + Theta)

Agora Theta:
  - (declined-run ledger — to be built)
  - scripts/engine_lifecycle.py                 — Lifecycle management
  - scripts/condense_board.py                   — Board condensation

Agora Thesis:
  - scripts/tradier_desk_read_model.py          — Desk read/attention model
  - scripts/tradier_desk_action_model.py        — Action recommendation model
  - scripts/tradier_cli_render_model.py         — CLI rendering model

Agora Ledger:
  - scripts/tradier_account.py                 — Account state & tracking
  - agora/hub/agora_server.py `/api/agora/asset-manager` — Connected-account NAV, allocation, risk, gate, and ledger aggregator
```

## Discord Channel Map (Tradier)
- **Alpha/Beta output channel:** `1483025184775733319` (#trading-desk)
- **Ledger/journaling:** #trading_journal
- **Coordination:** #hq_alfred
- **Live positions / Thesis monitoring:** `1483580321126416565`

## Command Semantics (Tradier)
- Leaders-board → candidates, not automatic entries
- `/take <contract>` → human authorizes Alfred execution
- `/reject <contract>` → decline candidate
- `/in <details>` → register manual entry for monitoring
- `/out <details>` → register exit, stop monitoring

## Risk Posture (Tradier)
- Scalp/directional options
- Disciplined, evidence-based
- No hype entries
- No contradictory tickets

## Continuity Recovery Order
1. `AGORA_OPERATING_STATE.md`
2. `/agora/` directory — per-division READMEs
3. `USER.md`
4. Recent daily notes in `memory/`
5. Division-specific scripts and artifacts

## Related but Separate Projects
| Project | Trigger | Channel | Role |
|---|---|---|---|
| Kalshi | `/coinflip` | `1483308037111283784` | Prediction-market engine (probability-first) |
| Uniswap rotator | daemon | `eth-scalper.service` | On-chain execution bot on Bazaar droplet |
