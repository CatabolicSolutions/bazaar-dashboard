from __future__ import annotations

from typing import Any


DECISION_STATES = {
    'proposed': {
        'authorized': False,
        'terminal': False,
    },
    'approved': {
        'authorized': True,
        'terminal': False,
    },
    'rejected': {
        'authorized': False,
        'terminal': True,
    },
    'revoked': {
        'authorized': False,
        'terminal': True,
    },
}


def intent_decision_for_intent(intent: dict[str, Any]) -> dict[str, Any]:
    decision_state = intent.get('decision_state') or 'proposed'
    decision_actor = intent.get('decision_actor') or 'system'
    decision_note = intent.get('decision_note') or ''

    if decision_state not in DECISION_STATES:
        raise ValueError(f'Unknown decision_state: {decision_state}')

    rules = DECISION_STATES[decision_state]
    return {
        'decision_state': decision_state,
        'decision_actor': decision_actor,
        'decision_note': decision_note,
        'is_authorized': rules['authorized'],
        'is_decision_terminal': rules['terminal'],
    }
