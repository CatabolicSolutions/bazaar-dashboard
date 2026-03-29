from __future__ import annotations

from typing import Any

from tradier_ui_render_model import render_tradier_ui_shell
from tradier_web_server import dispatch_request


def run_tradier_ui_page_flow(action_name: str, *, intent_id: str | None = None, params: dict[str, Any] | None = None, latest_limit: int = 20) -> dict[str, Any]:
    params = params or {}
    detail_query = f"&detail_intent_id={intent_id}" if intent_id else ''
    initial_status, initial_shell = dispatch_request('GET', f'/shell?latest_limit={latest_limit}{detail_query}')
    initial_render = render_tradier_ui_shell(initial_shell)

    selected_intent_id = intent_id
    if selected_intent_id is None:
        selected_intent_id = initial_shell['data']['selected_detail']['intent_id'] if initial_shell['data']['selected_detail'] else None

    action_status, action_response = dispatch_request('POST', '/shell/action', {
        'intent_id': selected_intent_id,
        'action_name': action_name,
        'params': params,
        'latest_limit': latest_limit,
    })

    refreshed_status = None
    refreshed_shell = None
    refreshed_render = None
    if action_response.get('status') == 'ok':
        refreshed_shell = action_response['data']['shell']
        refreshed_status = 200
        refreshed_render = render_tradier_ui_shell(refreshed_shell)

    return {
        'initial': {
            'status_code': initial_status,
            'shell': initial_shell,
            'render': initial_render,
        },
        'action': {
            'status_code': action_status,
            'response': action_response,
        },
        'refreshed': {
            'status_code': refreshed_status,
            'shell': refreshed_shell,
            'render': refreshed_render,
        },
    }
