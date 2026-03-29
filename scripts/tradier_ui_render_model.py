from __future__ import annotations

from typing import Any


def render_tradier_ui_shell(shell_response: dict[str, Any]) -> dict[str, Any]:
    shell = shell_response['data']
    selected = shell['selected_detail']

    return {
        'kind': 'tradier.ui_render_model',
        'header': {
            'title': 'Tradier Operator Shell',
            'status': shell_response['status'],
        },
        'overview_panel': shell['overview']['summary'],
        'worklist_panel': [
            {
                'intent_id': item['snapshot']['intent_id'],
                'priority_category': item['priority_category'],
                'priority_rank': item['priority_rank'],
                'operator_state': item['snapshot']['operator']['operator_state'],
            }
            for item in shell['worklist']['items']
        ],
        'detail_panel': {
            'intent_id': selected['intent_id'] if selected else None,
            'core': selected['core'] if selected else None,
            'operator': selected['operator_context']['operator'] if selected else None,
            'recent_context': selected['recent_context'] if selected else None,
        },
        'actions_panel': selected['operator_context']['actions'] if selected else None,
    }
