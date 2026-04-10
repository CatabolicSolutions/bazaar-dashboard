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
    'cash_day_trade': {
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
    account_type = str(account_snapshot.get('account_type') or '').lower()
    if account_type == 'cash':
        for key in ('cash_available', 'total_cash', 'stock_buying_power', 'option_buying_power'):
            value = account_snapshot.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return 0.0

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


def _build_decision_card(intent: ExecutionIntent, checks: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    disposition = 'accepted for execution' if not reasons else ('surfaced for review' if checks.get('review_only') else 'rejected')
    return {
        'symbol': intent.symbol,
        'direction': intent.side,
        'contract': intent.contract,
        'setup_type': intent.strategy_type.replace('_', ' '),
        'entry_logic': checks.get('entry_logic', 'leader-driven entry'),
        'trigger_condition': checks.get('trigger_condition', 'candidate selected by automation'),
        'invalidation_logic': checks.get('invalidation_logic', 'premium stop / thesis break'),
        'target_exit_logic': checks.get('target_exit_logic', 'intraday target or timeout exit'),
        'market_regime': checks.get('market_regime', 'unclassified'),
        'confidence': checks.get('confidence_score', 0),
        'risk_classification': checks.get('risk_classification', 'smallest_size_cash_account'),
        'why_now': '' if reasons else checks.get('why_now', 'candidate passed pre-trade gates'),
        'why_not': reasons,
        'rejection_reason': reasons[0] if reasons else '',
        'disposition': disposition,
    }


def evaluate_intent(intent: ExecutionIntent, account_snapshot: dict[str, Any], mark_price: float | None = None, open_positions: list[dict[str, Any]] | None = None) -> RiskDecision:
    policy = DEFAULT_POLICY[intent.mode]
    reasons: list[str] = []
    checks: dict[str, Any] = {
        'mode': intent.mode,
        'strategy_allowed': intent.strategy_type in policy['allowed_strategies'],
        'qty_within_cap': intent.qty <= policy['max_qty'],
        'time_in_force_day_only': intent.time_in_force == 'day',
        'account_ready_flag': bool(account_snapshot.get('ready_for_options_execution', True)),
        'account_type': account_snapshot.get('account_type'),
        'cash_account_day_trading_mode': bool(account_snapshot.get('cash_account_day_trading_mode', False)),
        'open_positions_count': len(open_positions or []),
        'market_regime': 'unclassified',
        'confidence_score': 0,
        'entry_logic': 'leader-driven entry',
        'trigger_condition': 'candidate selected by automation',
        'invalidation_logic': 'premium stop / thesis break',
        'target_exit_logic': 'intraday target or timeout exit',
        'risk_classification': 'smallest_size_cash_account',
        'why_now': 'candidate passed pre-trade gates',
        'review_only': False,
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

    if checks['cash_account_day_trading_mode'] and intent.strategy_type not in {'long_call', 'long_put'}:
        reasons.append('cash-account automation only allows long single-leg options')

    buying_power = _extract_option_buying_power(account_snapshot)
    checks['buying_power_reference'] = buying_power
    if notional is not None and buying_power > 0 and notional > buying_power:
        reasons.append(f'estimated notional {notional:.2f} exceeds buying power reference {buying_power:.2f}')

    ok, reason, drift_checks = validate_limit_drift(intent, mark_price, policy)
    checks['manual_limit_drift'] = drift_checks
    if not ok and reason:
        reasons.append(reason)

    decision_card = _build_decision_card(intent, checks, reasons)
    return RiskDecision(
        intent_id=intent.intent_id,
        mode=intent.mode,
        allowed=not reasons,
        reasons=reasons,
        checks=checks,
        decision_card=decision_card,
        disposition=decision_card['disposition'],
    )
