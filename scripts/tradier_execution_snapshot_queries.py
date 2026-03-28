from __future__ import annotations

from typing import Any

from tradier_execution_snapshot_api import get_execution_intent_snapshot_payload
from tradier_state_store import load_state

SNAPSHOT_COLLECTION_KIND = 'tradier.execution_intent_snapshot_collection'


def _all_intents() -> list[dict[str, Any]]:
    state = load_state()
    return list(state.get('intents', []))


def get_execution_snapshot_by_intent_id(intent_id: str) -> dict[str, Any] | None:
    for intent in _all_intents():
        if intent.get('intent_id') == intent_id:
            return get_execution_intent_snapshot_payload(intent)
    return None


def list_latest_execution_snapshots(limit: int = 10) -> dict[str, Any]:
    intents = _all_intents()
    items = [get_execution_intent_snapshot_payload(intent) for intent in intents[-limit:]]
    return {
        'kind': SNAPSHOT_COLLECTION_KIND,
        'query': {'mode': 'latest', 'limit': limit},
        'count': len(items),
        'items': items,
    }


def filter_execution_snapshots_by_field(field: str, value: Any, *, limit: int = 50) -> dict[str, Any]:
    intents = [intent for intent in _all_intents() if intent.get(field) == value]
    items = [get_execution_intent_snapshot_payload(intent) for intent in intents[:limit]]
    return {
        'kind': SNAPSHOT_COLLECTION_KIND,
        'query': {'mode': 'filter', 'field': field, 'value': value, 'limit': limit},
        'count': len(items),
        'items': items,
    }
