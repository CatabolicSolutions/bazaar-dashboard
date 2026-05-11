# Rotator War Room — Live Rebuild Roadmap

**Status**: Phase 1 in progress (2026-05-11)
**Objective**: Replace auto-generated research template (`uniswap-rotator.html`) with a data-driven page where every number comes from the live API.

## Architecture

| Layer | Detail |
|---|---|
| Source of truth | `GET /api/uniswap-rotator/state` — polled every 5s |
| API shape | `{summary, portfolio, performance, strategy, execution, risk, research, timeline[], chart_points[], service}` |
| Fallback | Snapshot JSON loaded at page load, then overwritten on first successful API poll |
| No build step | Single `.html` file, Tailwind CDN + lucide icons |
| Deploy path | git commit → git pull on droplet → page served by serve_dashboard.py on port 8765 |

## Panels

### 1. Status Bar (always visible)
SERVICE → `service.status` · MODE → `execution.mode` · SIDE → `summary.current_side` · ACTION → `summary.action` · THESIS → `summary.reason` · PORTFOLIO → `portfolio.portfolio_usd` · ETH-EQUIV → `portfolio.portfolio_eth_equiv` · LAST DECISION → `summary.last_decision_age_seconds` · FEED CONF → `summary.feed_confidence` · ANOMALY → `risk.alerts`

### 2. Overview Panel
TOTAL PORTFOLIO card, CURRENT SIDE card, DECISION ENGINE card, EXECUTION MODE card, Equity curve chart, Allocation chart, GUARDS & CONTROLS, LAST EVENTS table, ANOMALY SUMMARY

### 3. Position Panel
WETH card (balance, USD value, basis, EMA distances), CBBTC card, USDC card, DETAILED POSITION TABLE

### 4. Strategy Panel
Score cards, Edge, Entry/Exit targets, Signal state, Churn guard, EMA12/50, ETH/BTC Score History chart

### 5. Market Panel
WETH/USD 30D chart, BTC/USD 30D chart, ETH/BTC ratio chart, Spread score chart, Market data summary

### 6. Timeline Panel
Filterable event table (50 events), type filter, date range, search, event count

### 7. Execution Panel
Transport info, Last quote, Preflight, Execution attempt table, Execution quality chart

### 8. Risk Panel
Guard cards, Recent failures, Operator Controls (action buttons), Risk params

### 9. Performance Panel
PnL summary, Win rate, Equity curves, Performance metrics table, Fee/Gas drag

### 10. Research Panel
Last Replay Result, Tuning Battery, Athena Status, Vigil Status, Harness (all labeled with timestamps)

### 11. Diagnostics Panel
Anomaly history, Service health, State consistency, Recent errors

## Phases

### Phase 1 — Core Live Panels ✅ (current)
Status bar, Overview, Position, Strategy, Market, Timeline, Execution

### Phase 2 — Analytics + Research
Performance panel, Research panel (Athena/Vigil/Harness/Tuning), Diagnostics panel, Action buttons

### Phase 3 — Operator Controls
Live action buttons (reconcile, halt/resume, quote bridge), Settings modal, Export/Diagnostics download

## Design Principles
- Every number from API — zero hardcoded values
- Live data labeled with green dot, research data labeled with amber dot
- Charts without data show "Accumulating — data available after N hours"
- Empty states show messages, not silent nothingness
- Same dark theme, same status bar, same sidebar navigation
- Poll interval: 5s live data
- All error states gracefully handled (retry on failure, cached fallback + warning)
