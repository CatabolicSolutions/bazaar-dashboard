from __future__ import annotations

from typing import Any

from tradier_web_server import dispatch_request


def run_tradier_browser_page_flow(action_name: str, *, intent_id: str | None = None, params: dict[str, Any] | None = None, latest_limit: int = 20) -> dict[str, Any]:
    params = params or {}
    detail_query = f"&detail_intent_id={intent_id}" if intent_id else ''
    initial_status, initial_page = dispatch_request('GET', f'/app?latest_limit={latest_limit}{detail_query}')

    selected_intent_id = intent_id
    if selected_intent_id is None:
        selected_intent_id = initial_page['data']['render_model']['detail_panel']['intent_id']

    action_status, action_response = dispatch_request('POST', '/shell/action', {
        'intent_id': selected_intent_id,
        'action_name': action_name,
        'params': params,
        'latest_limit': latest_limit,
    })

    refreshed_status = None
    refreshed_page = None
    if action_response.get('status') == 'ok':
        refreshed_status, refreshed_page = dispatch_request('GET', f'/app?latest_limit={latest_limit}&detail_intent_id={selected_intent_id}')

    return {
        'initial': {'status_code': initial_status, 'page': initial_page},
        'action': {'status_code': action_status, 'response': action_response},
        'refreshed': {'status_code': refreshed_status, 'page': refreshed_page},
    }
