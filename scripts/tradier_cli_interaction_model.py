from __future__ import annotations

from typing import Any

from tradier_cli_render_model import render_tradier_cli_product_shell

CLI_INTERACTION_MODEL_KIND = 'tradier.cli_interaction_model'


def build_tradier_cli_interaction_model(*, latest_limit: int = 20, selected_intent_id: str | None = None) -> dict[str, Any]:
    rendered = render_tradier_cli_product_shell(latest_limit=latest_limit, detail_intent_id=selected_intent_id)
    selected_detail = rendered['selected_detail']

    selectable_items = [
        {
            'intent_id': item['intent_id'],
            'priority_category': item['priority_category'],
            'priority_rank': item['priority_rank'],
        }
        for item in rendered['prioritized_worklist']
    ]

    invocation = None
    if selected_detail is not None:
        invocation = {
            'intent_id': selected_detail['intent_id'],
            'allowed_actions': selected_detail['actions'],
            'invoke_contract': {
                'required_fields': ['intent_id', 'action_name'],
                'optional_fields': ['params'],
            },
        }

    return {
        'kind': CLI_INTERACTION_MODEL_KIND,
        'worklist': selectable_items,
        'selected_detail': selected_detail,
        'action_invocation': invocation,
    }


def build_cli_action_invocation(intent_id: str, action_name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        'intent_id': intent_id,
        'action_name': action_name,
        'params': params or {},
    }
