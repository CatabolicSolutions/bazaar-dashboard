from __future__ import annotations

from typing import Any

from tradier_execution_context import execution_context_for_intent
from tradier_execution_models import validate_persisted_intent_lifecycle


OPERATOR_STATE_BY_STATUS = {
    'candidate': 'draft',
    'queued': 'queued_for_review',
    'previewed': 'awaiting_approval',
    'approved': 'ready_to_send',
    'committed': 'sent_to_broker',
    'entered': 'live_position',
    'rejected': 'closed_rejected',
    'cancelled': 'closed_cancelled',
    'exited': 'closed_exited',
}

OPERATOR_STAGE_BY_STATUS = {
    'candidate': 'intake',
    'queued': 'intake',
    'previewed': 'review',
    'approved': 'execution',
    'committed': 'execution',
    'entered': 'position',
    'rejected': 'closed',
    'cancelled': 'closed',
    'exited': 'closed',
}

OPERATOR_ACTION_BY_STATUS = {
    'candidate': 'queue_or_reject',
    'queued': 'preview_or_reject',
    'previewed': 'approve_reject_or_cancel',
    'approved': 'commit_reject_or_cancel',
    'committed': 'await_entry_or_cancel',
    'entered': 'manage_exit',
    'rejected': 'none',
    'cancelled': 'none',
    'exited': 'none',
}


def interpret_operator_execution_state(intent: dict[str, Any]) -> dict[str, Any]:
    validate_persisted_intent_lifecycle(intent)
    status = intent['status']
    history = list(intent.get('transition_history') or [])
    latest = history[-1] if history else None
    context = execution_context_for_intent(intent)

    return {
        'intent_id': intent.get('intent_id'),
        'status': status,
        'operator_state': OPERATOR_STATE_BY_STATUS[status],
        'operator_stage': OPERATOR_STAGE_BY_STATUS[status],
        'next_operator_action': OPERATOR_ACTION_BY_STATUS[status],
        'is_terminal': status in {'rejected', 'cancelled', 'exited'},
        'history_count': len(history),
        'latest_transition': latest,
        'execution_context': context,
    }
