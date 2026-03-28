from __future__ import annotations

from typing import Any

from tradier_execution_governance import validate_execution_contract_combinations

SNAPSHOT_SERIALIZATION_VERSION = 1


def serialize_execution_intent_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    validate_execution_contract_combinations({
        'lifecycle': snapshot['lifecycle'],
        'decision': snapshot['decision'],
        'readiness': snapshot['readiness'],
        'outcome': snapshot['outcome'],
        'escalation': snapshot['escalation'],
        'timing': snapshot['timing'],
        'external_reference': snapshot['external_reference'],
        'execution_attempt': snapshot['execution_attempt'],
        'reconciliation': snapshot['reconciliation'],
    })
    return {
        'snapshot_version': SNAPSHOT_SERIALIZATION_VERSION,
        'snapshot': snapshot,
    }


def deserialize_execution_intent_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    version = payload.get('snapshot_version')
    if version != SNAPSHOT_SERIALIZATION_VERSION:
        raise ValueError(f'Unsupported snapshot_version: {version}')

    snapshot = payload['snapshot']
    validate_execution_contract_combinations({
        'lifecycle': snapshot['lifecycle'],
        'decision': snapshot['decision'],
        'readiness': snapshot['readiness'],
        'outcome': snapshot['outcome'],
        'escalation': snapshot['escalation'],
        'timing': snapshot['timing'],
        'external_reference': snapshot['external_reference'],
        'execution_attempt': snapshot['execution_attempt'],
        'reconciliation': snapshot['reconciliation'],
    })
    return snapshot
