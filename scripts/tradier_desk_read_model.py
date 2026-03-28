from __future__ import annotations

from typing import Any

from tradier_execution_snapshot_queries import list_latest_execution_snapshots

DESK_READ_MODEL_KIND = 'tradier.trading_desk_read_model'


def build_trading_desk_read_model(*, latest_limit: int = 20) -> dict[str, Any]:
    latest_payload = list_latest_execution_snapshots(limit=latest_limit)
    items = latest_payload['items']

    ready_intents = [
        item for item in items
        if item['snapshot']['readiness']['readiness_state'] == 'ready'
        and item['snapshot']['lifecycle']['status'] == 'approved'
        and item['snapshot']['escalation']['escalation_state'] == 'no_escalation'
        and item['snapshot']['timing']['is_actionable']
    ]
    blocked_intents = [item for item in items if item['snapshot']['escalation']['escalation_state'] == 'blocked']
    pending_confirmation_intents = [
        item for item in items if item['snapshot']['reconciliation']['reconciliation_state'] == 'pending_confirmation'
    ]
    divergent_intents = [item for item in items if item['snapshot']['reconciliation']['reconciliation_state'] == 'divergent']

    return {
        'kind': DESK_READ_MODEL_KIND,
        'source': {
            'kind': latest_payload['kind'],
            'query': latest_payload['query'],
            'count': latest_payload['count'],
        },
        'views': {
            'ready_intents': ready_intents,
            'blocked_intents': blocked_intents,
            'pending_confirmation_intents': pending_confirmation_intents,
            'divergent_intents': divergent_intents,
            'latest_activity': items,
        },
    }
