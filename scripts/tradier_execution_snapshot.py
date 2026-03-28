from __future__ import annotations

from typing import Any

from tradier_execution_semantics import interpret_operator_execution_state
from tradier_execution_models import validate_persisted_intent_lifecycle


def build_execution_intent_snapshot(intent: dict[str, Any]) -> dict[str, Any]:
    validate_persisted_intent_lifecycle(intent)
    operator_view = interpret_operator_execution_state(intent)

    lifecycle = {
        'status': intent['status'],
        'history_count': len(intent.get('transition_history') or []),
        'latest_transition': operator_view['latest_transition'],
    }

    return {
        'intent_id': intent.get('intent_id'),
        'lifecycle': lifecycle,
        'decision': operator_view['decision'],
        'readiness': operator_view['readiness'],
        'outcome': operator_view['outcome'],
        'escalation': operator_view['escalation'],
        'timing': operator_view['timing'],
        'external_reference': operator_view['external_reference'],
        'provenance': operator_view['provenance'],
        'execution_context': operator_view['execution_context'],
        'position_linkage': operator_view['position_linkage'],
        'operator': {
            'operator_state': operator_view['operator_state'],
            'operator_stage': operator_view['operator_stage'],
            'next_operator_action': operator_view['next_operator_action'],
            'is_terminal': operator_view['is_terminal'],
        },
    }
