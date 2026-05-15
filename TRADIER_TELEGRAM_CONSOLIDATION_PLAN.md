# Tradier Telegram Consolidation Plan

## Target operating model
A single streamlined Tradier operating loop:

1. produce **2-3 leaders max**
2. provide richer **directional conviction + asymmetry rationale**
3. build a **human sign-off execution ticket**
4. monitor live open positions with **risk / stop / TP / exit posture**
5. send all operational communication through **Telegram first**
6. keep **Agora as a thin shell**, not the primary operator surface

## Keep
- `scripts/tradier_strategy_processor_v2.py`
- `scripts/tradier_ticket_formatter.py`
- `scripts/tradier_approval_flow.py`
- Tradier execution/account plumbing
- VPS deployment/runtime setup
- scoring and candidate-selection logic worth preserving

## Retire / sideline
- Discord-live-first routing for core operations
- noisy Trading Desk churn loops
- stale dashboard-heavy surfaces as primary workflow
- old desk model sprawl that does not directly support leaders -> signoff -> monitoring

## Thin-shell Agora
Keep only:
- lightweight overview / read-only shell
- optional summary surface
- no heavy primary workflow dependency

## Canonical flow
### 1) Leader run
Output only the top 2-3 candidates.
Each leader should include:
- symbol / contract
- directional thesis
- asymmetry / structure rationale
- entry reference
- invalidation
- confidence

### 2) Sign-off ticket
Before execution, generate a concise Telegram ticket:
- contract
- why now
- risk line
- TP / exit path
- exact action to approve

### 3) Open-position monitoring
Once in a position, updates should become rolling state reports:
- current posture
- confidence
- whether move is working / stalling / failing
- TP1 proximity
- stop / invalidation proximity
- exit recommendation when needed

### 4) Exit/offramp alerts
Telegram alert when:
- TP1 reached
- stop / invalidation threatened
- structure breaks
- one-click / explicit exit recommendation should be presented

## Implementation slices
### Slice 1
- define canonical Telegram message formats
- preserve Tradier leader + approval plumbing
- stop treating Discord as the default live ops lane

### Slice 2
- connect open-position monitoring to Telegram-first updates
- build cleaner risk/TP/exit alerts

### Slice 3
- reduce Agora to a thin shell
- remove or bypass stale dashboard/desk dependency from the main operator flow

## Initial audit notes
Files most aligned with the new operating model:
- `scripts/tradier_strategy_processor_v2.py`
- `scripts/tradier_ticket_formatter.py`
- `scripts/tradier_approval_flow.py`
- `scripts/tradier_position_monitor.py`

Files likely to be reduced in importance or bypassed:
- `scripts/tradier_desk_action_model.py`
- `scripts/tradier_desk_prioritization_model.py`
- `scripts/tradier_desk_read_model.py`
- `scripts/tradier_desk_summary_model.py`
- `scripts/tradier_dashboard_attention_feed_model.py`
- `scripts/tradier_dashboard_detail_model.py`
- `scripts/tradier_dashboard_overview_model.py`
- `scripts/tradier_web_server.py`
- `scripts/tradier_web_shell_action_endpoint.py`
- `scripts/tradier_web_shell_endpoint.py`
- `scripts/tradier_web_shell_model.py`

## Delivery lane
Preferred target:
- `bloc_bazaar_bot`

Fallback:
- current direct Telegram chat
