from __future__ import annotations

from typing import Any


ATTEMPT_STATES = {
    'no_attempt': {
        'is_in_progress': False,
        'is_complete': False,
        'is_failed': False,
    },
    'attempt_in_progress': {
        'is_in_progress': True,
        'is_complete': False,
        'is_failed': False,
    },
    'attempt_completed': {
        'is_in_progress': False,
        'is_complete': True,
        'is_failed': False,
    },
    'attempt_failed': {
        'is_in_progress': False,
        'is_complete': True,
        'is_failed': True,
    },
    'retried_attempts': {
        'is_in_progress': False,
        'is_complete': True,
        'is_failed': False,
    },
}


def intent_execution_attempt_for_intent(intent: dict[str, Any]) -> dict[str, Any]:
    attempt_state = intent.get('attempt_state') or 'no_attempt'
    attempt_count = int(intent.get('attempt_count') or 0)
    latest_attempt_id = intent.get('latest_attempt_id')
    latest_attempt_note = intent.get('latest_attempt_note') or ''

    if attempt_state not in ATTEMPT_STATES:
        raise ValueError(f'Unknown attempt_state: {attempt_state}')
    if attempt_count < 0:
        raise ValueError('attempt_count must be >= 0')

    rules = ATTEMPT_STATES[attempt_state]
    if attempt_state == 'no_attempt' and attempt_count != 0:
        raise ValueError('no_attempt state requires attempt_count == 0')
    if attempt_state != 'no_attempt' and attempt_count == 0:
        raise ValueError(f'{attempt_state} requires attempt_count > 0')

    return {
        'attempt_state': attempt_state,
        'attempt_count': attempt_count,
        'latest_attempt_id': latest_attempt_id,
        'latest_attempt_note': latest_attempt_note,
        'is_in_progress': rules['is_in_progress'],
        'is_attempt_complete': rules['is_complete'],
        'is_attempt_failed': rules['is_failed'],
        'has_multiple_attempts': attempt_count > 1,
    }
