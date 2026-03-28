from __future__ import annotations

from typing import Any

from tradier_execution_snapshot import build_execution_intent_snapshot
from tradier_execution_snapshot_serialization import serialize_execution_intent_snapshot

SNAPSHOT_API_KIND = 'tradier.execution_intent_snapshot'


def get_execution_intent_snapshot_payload(intent: dict[str, Any]) -> dict[str, Any]:
    snapshot = build_execution_intent_snapshot(intent)
    payload = serialize_execution_intent_snapshot(snapshot)
    return {
        'kind': SNAPSHOT_API_KIND,
        **payload,
    }
