from __future__ import annotations

from typing import Any


RECONCILIATION_STATES = {
    'not_reconciled': {
        'is_aligned': False,
        'is_pending_confirmation': False,
        'has_mismatch': False,
    },
    'reconciled': {
        'is_aligned': True,
        'is_pending_confirmation': False,
        'has_mismatch': False,
    },
    'pending_confirmation': {
        'is_aligned': False,
        'is_pending_confirmation': True,
        'has_mismatch': False,
    },
    'divergent': {
        'is_aligned': False,
        'is_pending_confirmation': False,
        'has_mismatch': True,
    },
}


def intent_reconciliation_for_intent(intent: dict[str, Any]) -> dict[str, Any]:
    reconciliation_state = intent.get('reconciliation_state') or 'not_reconciled'
    reconciliation_note = intent.get('reconciliation_note') or ''

    if reconciliation_state not in RECONCILIATION_STATES:
        raise ValueError(f'Unknown reconciliation_state: {reconciliation_state}')

    rules = RECONCILIATION_STATES[reconciliation_state]
    return {
        'reconciliation_state': reconciliation_state,
        'reconciliation_note': reconciliation_note,
        'is_aligned': rules['is_aligned'],
        'is_pending_confirmation': rules['is_pending_confirmation'],
        'has_mismatch': rules['has_mismatch'],
    }
