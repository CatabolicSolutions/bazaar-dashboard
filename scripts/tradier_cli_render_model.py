from __future__ import annotations

from typing import Any

from tradier_product_shell_model import build_tradier_product_shell_model

CLI_RENDER_MODEL_KIND = 'tradier.cli_render_model'


def render_tradier_cli_product_shell(*, latest_limit: int = 20, detail_intent_id: str | None = None) -> dict[str, Any]:
    shell = build_tradier_product_shell_model(latest_limit=latest_limit, detail_intent_id=detail_intent_id)

    overview = shell['overview']['summary']
    worklist = shell['worklist']['items']
    detail = shell['detail']

    rendered_worklist = [
        {
            'intent_id': item['snapshot']['intent_id'],
            'priority_category': item['priority_category'],
            'priority_rank': item['priority_rank'],
            'operator_state': item['snapshot']['operator']['operator_state'],
            'symbol': item['snapshot']['execution_context']['mode'] + ':' + item['snapshot']['provenance']['strategy_source'],
        }
        for item in worklist
    ]

    rendered_detail = None
    if detail is not None:
        rendered_detail = {
            'intent_id': detail['intent_id'],
            'core': detail['core'],
            'operator': detail['operator_context']['operator'],
            'actions': detail['operator_context']['actions'],
            'recent_context': detail['recent_context'],
        }

    return {
        'kind': CLI_RENDER_MODEL_KIND,
        'overview_summary': overview,
        'prioritized_worklist': rendered_worklist,
        'selected_detail': rendered_detail,
        'selected_actions': rendered_detail['actions'] if rendered_detail else None,
    }
