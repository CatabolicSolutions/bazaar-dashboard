from __future__ import annotations

from typing import Any


ESCALATION_STATES = {
    'no_escalation': {
        'needs_operator_attention': False,
        'blocks_autonomous_progress': False,
        'terminal_attention_state': False,
    },
    'warning': {
        'needs_operator_attention': True,
        'blocks_autonomous_progress': False,
        'terminal_attention_state': False,
    },
    'blocked': {
        'needs_operator_attention': True,
        'blocks_autonomous_progress': True,
        'terminal_attention_state': False,
    },
    'terminal_failure': {
        'needs_operator_attention': True,
        'blocks_autonomous_progress': True,
        'terminal_attention_state': True,
    },
}


def intent_escalation_for_intent(intent: dict[str, Any]) -> dict[str, Any]:
    escalation_state = intent.get('escalation_state') or 'no_escalation'
    escalation_reason = intent.get('escalation_reason') or ''

    if escalation_state not in ESCALATION_STATES:
        raise ValueError(f'Unknown escalation_state: {escalation_state}')

    rules = ESCALATION_STATES[escalation_state]
    return {
        'escalation_state': escalation_state,
        'escalation_reason': escalation_reason,
        'needs_operator_attention': rules['needs_operator_attention'],
        'blocks_autonomous_progress': rules['blocks_autonomous_progress'],
        'is_terminal_attention_state': rules['terminal_attention_state'],
    }
