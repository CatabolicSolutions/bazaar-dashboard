from __future__ import annotations

from typing import Any

from tradier_desk_read_model import build_trading_desk_read_model

DESK_ACTION_MODEL_KIND = 'tradier.trading_desk_action_model'


def actions_for_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    reconciliation_state = snapshot['reconciliation']['reconciliation_state']
    escalation_state = snapshot['escalation']['escalation_state']
    readiness_state = snapshot['readiness']['readiness_state']
    lifecycle_status = snapshot['lifecycle']['status']

    actions = {
        'approve_intent': {'available': False, 'service_method': 'approve_intent'},
        'mark_intent_ready': {'available': False, 'service_method': 'mark_intent_ready'},
        'begin_execution_attempt': {'available': False, 'service_method': 'begin_execution_attempt'},
        'block_intent': {'available': False, 'service_method': 'block_intent'},
        'retry_execution_attempt': {'available': False, 'service_method': 'retry_execution_attempt'},
        'reconcile_intent': {'available': False, 'service_method': 'reconcile_intent'},
        'invalidate_external_reference': {'available': False, 'service_method': 'invalidate_external_reference'},
    }

    if lifecycle_status == 'approved' and readiness_state == 'ready' and escalation_state == 'no_escalation':
        actions['begin_execution_attempt']['available'] = True
        actions['block_intent']['available'] = True

    if escalation_state == 'blocked':
        actions['retry_execution_attempt']['available'] = True

    if reconciliation_state == 'pending_confirmation':
        actions['reconcile_intent']['available'] = True

    if reconciliation_state == 'divergent':
        actions['invalidate_external_reference']['available'] = True

    return actions


def build_trading_desk_action_model(*, latest_limit: int = 20) -> dict[str, Any]:
    desk = build_trading_desk_read_model(latest_limit=latest_limit)
    views = desk['views']

    return {
        'kind': DESK_ACTION_MODEL_KIND,
        'source': desk['source'],
        'views': {
            'ready_intents': [
                {'snapshot': item['snapshot'], 'actions': actions_for_snapshot(item['snapshot'])}
                for item in views['ready_intents']
            ],
            'blocked_intents': [
                {'snapshot': item['snapshot'], 'actions': actions_for_snapshot(item['snapshot'])}
                for item in views['blocked_intents']
            ],
            'pending_confirmation_intents': [
                {'snapshot': item['snapshot'], 'actions': actions_for_snapshot(item['snapshot'])}
                for item in views['pending_confirmation_intents']
            ],
            'divergent_intents': [
                {'snapshot': item['snapshot'], 'actions': actions_for_snapshot(item['snapshot'])}
                for item in views['divergent_intents']
            ],
            'latest_activity': [
                {'snapshot': item['snapshot'], 'actions': actions_for_snapshot(item['snapshot'])}
                for item in views['latest_activity']
            ],
        },
    }
