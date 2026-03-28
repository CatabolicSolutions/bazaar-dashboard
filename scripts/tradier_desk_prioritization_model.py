from __future__ import annotations

from typing import Any

from tradier_desk_action_model import build_trading_desk_action_model

DESK_PRIORITIZATION_MODEL_KIND = 'tradier.trading_desk_prioritization_model'

PRIORITY_BY_CATEGORY = {
    'divergent': 1,
    'blocked': 2,
    'pending_confirmation': 3,
    'ready': 4,
    'other': 9,
}


def categorize_snapshot_for_priority(snapshot: dict[str, Any]) -> str:
    if snapshot['reconciliation']['reconciliation_state'] == 'divergent':
        return 'divergent'
    if snapshot['escalation']['escalation_state'] == 'blocked':
        return 'blocked'
    if snapshot['reconciliation']['reconciliation_state'] == 'pending_confirmation':
        return 'pending_confirmation'
    if (
        snapshot['readiness']['readiness_state'] == 'ready'
        and snapshot['lifecycle']['status'] == 'approved'
        and snapshot['escalation']['escalation_state'] == 'no_escalation'
        and snapshot['timing']['is_actionable']
    ):
        return 'ready'
    return 'other'


def build_trading_desk_prioritization_model(*, latest_limit: int = 20) -> dict[str, Any]:
    action_model = build_trading_desk_action_model(latest_limit=latest_limit)
    items = action_model['views']['latest_activity']

    enriched = []
    for item in items:
        category = categorize_snapshot_for_priority(item['snapshot'])
        enriched.append({
            'snapshot': item['snapshot'],
            'actions': item['actions'],
            'priority_category': category,
            'priority_rank': PRIORITY_BY_CATEGORY[category],
        })

    enriched.sort(key=lambda item: (item['priority_rank'], item['snapshot']['intent_id']))

    return {
        'kind': DESK_PRIORITIZATION_MODEL_KIND,
        'source': action_model['source'],
        'items': enriched,
    }
