from __future__ import annotations

from typing import Any

from tradier_desk_action_model import actions_for_snapshot
from tradier_execution_service import TradierExecutionService
from tradier_execution_snapshot_api import get_execution_intent_snapshot_payload
from tradier_state_store import load_state
from tradier_web_shell_endpoint import get_tradier_web_shell_response

WEB_SHELL_ACTION_ENDPOINT_KIND = 'tradier.web_shell_action_endpoint_response'


def _load_intent_by_id(intent_id: str) -> dict[str, Any] | None:
    state = load_state()
    for intent in state.get('intents', []):
        if intent.get('intent_id') == intent_id:
            return intent
    return None


def _execute_action(intent: dict[str, Any], action_name: str, params: dict[str, Any]) -> dict[str, Any]:
    service = TradierExecutionService()
    action_map = {
        'mark_intent_ready': lambda: service.mark_intent_ready(intent, reason=params.get('reason', 'Ready via endpoint')),
        'block_intent': lambda: service.block_intent(intent, reason=params.get('reason', 'Blocked via endpoint'), escalation_state=params.get('escalation_state', 'blocked')),
        'retry_execution_attempt': lambda: service.retry_execution_attempt(intent, attempt_id=params['attempt_id'], reason=params.get('reason', 'Retry via endpoint')),
        'reconcile_intent': lambda: service.reconcile_intent(intent, note=params.get('note', 'Reconciled via endpoint')),
        'invalidate_external_reference': lambda: service.invalidate_external_reference(intent, note=params.get('note', 'Invalidated via endpoint')),
    }
    if action_name not in action_map:
        raise ValueError(f'Unsupported web action endpoint action: {action_name}')
    return action_map[action_name]()


def post_tradier_web_shell_action(intent_id: str, action_name: str, params: dict[str, Any] | None = None, *, latest_limit: int = 20) -> dict[str, Any]:
    params = params or {}
    intent = _load_intent_by_id(intent_id)
    if intent is None:
        return {
            'kind': WEB_SHELL_ACTION_ENDPOINT_KIND,
            'status': 'not_found',
            'error': f'Intent not found: {intent_id}',
            'data': None,
        }

    snapshot_payload = get_execution_intent_snapshot_payload(intent)
    actions = actions_for_snapshot(snapshot_payload['snapshot'])
    if not actions.get(action_name, {}).get('available', False):
        return {
            'kind': WEB_SHELL_ACTION_ENDPOINT_KIND,
            'status': 'rejected',
            'error': f'Action not allowed for intent: {action_name}',
            'data': {
                'intent_id': intent_id,
                'action_name': action_name,
                'allowed_actions': actions,
            },
        }

    result = _execute_action(intent, action_name, params)
    shell = get_tradier_web_shell_response(latest_limit=latest_limit, detail_intent_id=intent_id)
    return {
        'kind': WEB_SHELL_ACTION_ENDPOINT_KIND,
        'status': 'ok',
        'error': None,
        'data': {
            'intent_id': intent_id,
            'action_name': action_name,
            'action_result': result,
            'shell': shell,
        },
    }
