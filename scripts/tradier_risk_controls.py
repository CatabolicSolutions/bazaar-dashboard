from __future__ import annotations

from typing import Any

from tradier_execution_models import ExecutionIntent, RiskDecision


DEFAULT_POLICY = {
    'cash_day': {
        'allowed_strategies': {'long_call', 'long_put'},
        'max_qty': 10,
        'max_notional': 2500.0,
        'manual_limit_drift_pct': 0.05,
        'require_limit_price': False,
    },
    'margin_swing': {
        'allowed_strategies': {'long_call', 'long_put'},
        'max_qty': 20,
        'max_notional': 10000.0,
        'manual_limit_drift_pct': 0.03,
        'require_limit_price': False,
    },
}


def _extract_option_buying_power(account_snapshot: dict[str, Any]) -> float:
    for key in ('option_buying_power', 'stock_buying_power', 'total_cash'):
        value = account_snapshot.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return 0.0


def validate_limit_drift(intent: ExecutionIntent, mark_price: float | None, policy: dict[str, Any]) -> tuple[bool, str | None, dict[str, Any]]:
    checks = {'mark_price': mark_price, 'limit_price': intent.limit_price, 'max_drift_pct': policy['manual_limit_drift_pct']}
    if intent.limit_price is None or mark_price is None or mark_price <= 0:
        return True, None, checks
    drift_pct = abs(intent.limit_price - mark_price) / mark_price
    checks['drift_pct'] = drift_pct
    if drift_pct > policy['manual_limit_drift_pct']:
        return False, f'manual limit price drift {drift_pct:.2%} exceeds allowed {policy["manual_limit_drift_pct"]:.2%}', checks
    return True, None, checks


def evaluate_intent(intent: ExecutionIntent, account_snapshot: dict[str, Any], mark_price: float | None = None, open_positions: list[dict[str, Any]] | None = None) -> RiskDecision:
    policy = DEFAULT_POLICY[intent.mode]
    reasons: list[str] = []
    checks: dict[str, Any] = {
        'mode': intent.mode,
        'strategy_allowed': intent.strategy_type in policy['allowed_strategies'],
        'qty_within_cap': intent.qty <= policy['max_qty'],
        'time_in_force_day_only': intent.time_in_force == 'day',
        'account_ready_flag': bool(account_snapshot.get('ready_for_options_execution', True)),
        'open_positions_count': len(open_positions or []),
    }

    if not checks['strategy_allowed']:
        reasons.append(f"strategy {intent.strategy_type} not allowed in mode {intent.mode}")
    if not checks['qty_within_cap']:
        reasons.append(f"qty {intent.qty} exceeds max {policy['max_qty']} for mode {intent.mode}")
    if not checks['time_in_force_day_only']:
        reasons.append('only day TIF is allowed in v1')
    if not checks['account_ready_flag']:
        reasons.extend(account_snapshot.get('blockers', ['account not ready']))

    notional = None
    if intent.limit_price is not None:
        notional = float(intent.limit_price) * int(intent.qty) * 100.0
        checks['estimated_notional'] = notional
        if notional > policy['max_notional']:
            reasons.append(f'estimated notional {notional:.2f} exceeds max {policy["max_notional"]:.2f} for mode {intent.mode}')

    buying_power = _extract_option_buying_power(account_snapshot)
    checks['buying_power_reference'] = buying_power
    if notional is not None and buying_power > 0 and notional > buying_power:
        reasons.append(f'estimated notional {notional:.2f} exceeds buying power reference {buying_power:.2f}')

    ok, reason, drift_checks = validate_limit_drift(intent, mark_price, policy)
    checks['manual_limit_drift'] = drift_checks
    if not ok and reason:
        reasons.append(reason)

    return RiskDecision(
        intent_id=intent.intent_id,
        mode=intent.mode,
        allowed=not reasons,
        reasons=reasons,
        checks=checks,
    )
