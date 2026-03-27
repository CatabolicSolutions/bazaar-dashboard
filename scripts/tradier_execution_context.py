from __future__ import annotations

from typing import Any

from tradier_execution_models import VALID_MODES


EXECUTION_CONTEXT_BY_MODE = {
    'cash_day': {
        'domain': 'cash_day_trading',
        'operator_lane': 'day_trade',
        'holding_profile': 'intraday',
        'capital_treatment': 'cash_settled',
        'review_emphasis': 'speed_and_day_trade_rules',
    },
    'margin_swing': {
        'domain': 'margin_swing_trading',
        'operator_lane': 'swing_trade',
        'holding_profile': 'multi_session',
        'capital_treatment': 'margin_enabled',
        'review_emphasis': 'overnight_risk_and_carry',
    },
}


def execution_context_for_intent(intent: dict[str, Any]) -> dict[str, Any]:
    mode = intent.get('mode')
    if mode not in VALID_MODES:
        raise ValueError(f'Unknown execution mode: {mode}')

    context = EXECUTION_CONTEXT_BY_MODE[mode]
    return {
        'mode': mode,
        'domain': context['domain'],
        'operator_lane': context['operator_lane'],
        'holding_profile': context['holding_profile'],
        'capital_treatment': context['capital_treatment'],
        'review_emphasis': context['review_emphasis'],
    }
