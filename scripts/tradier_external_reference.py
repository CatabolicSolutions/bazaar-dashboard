from __future__ import annotations

from typing import Any


EXTERNAL_REFERENCE_STATES = {
    'no_external_reference': {
        'has_external_reference': False,
        'reference_pending': False,
        'reference_valid': False,
    },
    'pending_external_reference': {
        'has_external_reference': False,
        'reference_pending': True,
        'reference_valid': False,
    },
    'linked_external_reference': {
        'has_external_reference': True,
        'reference_pending': False,
        'reference_valid': True,
    },
    'invalid_external_reference': {
        'has_external_reference': True,
        'reference_pending': False,
        'reference_valid': False,
    },
}


def intent_external_reference_for_intent(intent: dict[str, Any]) -> dict[str, Any]:
    external_reference_state = intent.get('external_reference_state') or 'no_external_reference'
    external_reference_id = intent.get('external_reference_id')
    external_reference_system = intent.get('external_reference_system') or ''
    external_reference_note = intent.get('external_reference_note') or ''

    if external_reference_state not in EXTERNAL_REFERENCE_STATES:
        raise ValueError(f'Unknown external_reference_state: {external_reference_state}')

    rules = EXTERNAL_REFERENCE_STATES[external_reference_state]
    if rules['has_external_reference'] and not external_reference_id:
        raise ValueError(
            f'External reference state {external_reference_state} requires external_reference_id'
        )
    if not rules['has_external_reference'] and external_reference_id:
        raise ValueError(
            f'External reference state {external_reference_state} cannot carry external_reference_id'
        )

    return {
        'external_reference_state': external_reference_state,
        'external_reference_id': external_reference_id,
        'external_reference_system': external_reference_system,
        'external_reference_note': external_reference_note,
        'has_external_reference': rules['has_external_reference'],
        'reference_pending': rules['reference_pending'],
        'reference_valid': rules['reference_valid'],
    }
