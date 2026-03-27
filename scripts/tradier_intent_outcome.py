from __future__ import annotations

from typing import Any


OUTCOME_STATES = {
    'no_outcome': {
        'has_execution_effect': False,
        'is_complete': False,
        'is_failed': False,
    },
    'partial_execution': {
        'has_execution_effect': True,
        'is_complete': False,
        'is_failed': False,
    },
    'full_execution': {
        'has_execution_effect': True,
        'is_complete': True,
        'is_failed': False,
    },
    'failed_execution': {
        'has_execution_effect': False,
        'is_complete': True,
        'is_failed': True,
    },
}


def intent_outcome_for_intent(intent: dict[str, Any]) -> dict[str, Any]:
    outcome_state = intent.get('outcome_state') or 'no_outcome'
    outcome_reason = intent.get('outcome_reason') or ''
    effected_qty = intent.get('effected_qty')

    if outcome_state not in OUTCOME_STATES:
        raise ValueError(f'Unknown outcome_state: {outcome_state}')

    rules = OUTCOME_STATES[outcome_state]
    return {
        'outcome_state': outcome_state,
        'outcome_reason': outcome_reason,
        'effected_qty': effected_qty,
        'has_execution_effect': rules['has_execution_effect'],
        'is_outcome_complete': rules['is_complete'],
        'is_failed_execution': rules['is_failed'],
    }
