from __future__ import annotations

from typing import Any


TIMING_STATES = {
    'no_timing_pressure': {
        'is_urgent': False,
        'is_expired': False,
        'is_actionable': True,
    },
    'time_sensitive': {
        'is_urgent': True,
        'is_expired': False,
        'is_actionable': True,
    },
    'expired': {
        'is_urgent': False,
        'is_expired': True,
        'is_actionable': False,
    },
}


def intent_timing_for_intent(intent: dict[str, Any]) -> dict[str, Any]:
    timing_state = intent.get('timing_state') or 'no_timing_pressure'
    timing_reason = intent.get('timing_reason') or ''

    if timing_state not in TIMING_STATES:
        raise ValueError(f'Unknown timing_state: {timing_state}')

    rules = TIMING_STATES[timing_state]
    return {
        'timing_state': timing_state,
        'timing_reason': timing_reason,
        'is_urgent': rules['is_urgent'],
        'is_expired': rules['is_expired'],
        'is_actionable': rules['is_actionable'],
    }
