from __future__ import annotations

from typing import Any


READINESS_STATES = {
    'not_ready': {
        'executable_now': False,
        'blocked': False,
    },
    'ready': {
        'executable_now': True,
        'blocked': False,
    },
    'blocked': {
        'executable_now': False,
        'blocked': True,
    },
}


def intent_readiness_for_intent(intent: dict[str, Any]) -> dict[str, Any]:
    readiness_state = intent.get('readiness_state') or 'not_ready'
    readiness_reason = intent.get('readiness_reason') or ''

    if readiness_state not in READINESS_STATES:
        raise ValueError(f'Unknown readiness_state: {readiness_state}')

    rules = READINESS_STATES[readiness_state]
    return {
        'readiness_state': readiness_state,
        'readiness_reason': readiness_reason,
        'is_executable_now': rules['executable_now'],
        'is_blocked': rules['blocked'],
    }
