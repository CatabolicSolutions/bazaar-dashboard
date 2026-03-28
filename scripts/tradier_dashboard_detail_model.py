from __future__ import annotations

from typing import Any

from tradier_desk_action_model import actions_for_snapshot
from tradier_execution_snapshot_api import get_execution_intent_snapshot_payload

DASHBOARD_DETAIL_MODEL_KIND = 'tradier.dashboard_detail_model'


def build_tradier_dashboard_detail_model(intent: dict[str, Any]) -> dict[str, Any]:
    payload = get_execution_intent_snapshot_payload(intent)
    snapshot = payload['snapshot']

    return {
        'kind': DASHBOARD_DETAIL_MODEL_KIND,
        'snapshot_version': payload['snapshot_version'],
        'intent_id': snapshot['intent_id'],
        'core': {
            'lifecycle': snapshot['lifecycle'],
            'decision': snapshot['decision'],
            'readiness': snapshot['readiness'],
            'outcome': snapshot['outcome'],
            'escalation': snapshot['escalation'],
            'timing': snapshot['timing'],
        },
        'operator_context': {
            'operator': snapshot['operator'],
            'actions': actions_for_snapshot(snapshot),
        },
        'execution_context': snapshot['execution_context'],
        'position_linkage': snapshot['position_linkage'],
        'provenance': snapshot['provenance'],
        'external_reference': snapshot['external_reference'],
        'execution_attempt': snapshot['execution_attempt'],
        'reconciliation': snapshot['reconciliation'],
        'recent_context': {
            'latest_transition': snapshot['lifecycle']['latest_transition'],
            'history_count': snapshot['lifecycle']['history_count'],
            'latest_attempt_id': snapshot['execution_attempt']['latest_attempt_id'],
            'reconciliation_state': snapshot['reconciliation']['reconciliation_state'],
        },
    }
