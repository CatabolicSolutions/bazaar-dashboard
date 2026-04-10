from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradier_execution_governance import validate_execution_contract_combinations
from tradier_execution_models import now_iso, transition_intent, validate_persisted_intent_lifecycle
from tradier_execution_attempt import intent_execution_attempt_for_intent
from tradier_external_reference import intent_external_reference_for_intent
from tradier_intent_decision import intent_decision_for_intent
from tradier_intent_escalation import intent_escalation_for_intent
from tradier_intent_outcome import intent_outcome_for_intent
from tradier_intent_readiness import intent_readiness_for_intent
from tradier_intent_timing import intent_timing_for_intent
from tradier_reconciliation_state import intent_reconciliation_for_intent

ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = ROOT / 'out' / 'runtime_state'
LEGACY_DASHBOARD_STATE_ROOT = ROOT / 'dashboard' / 'state'
EXECUTION_STATE_PATH = STATE_ROOT / 'tradier_execution_state.json'
AUDIT_LOG_PATH = STATE_ROOT / 'tradier_audit_log.json'


def default_state() -> dict[str, Any]:
    return {
        'updatedAt': now_iso(),
        'intents': [],
        'previews': [],
        'orders': [],
        'positions': [],
        'riskDecisions': [],
    }


def load_json(path: Path, fallback: Any):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding='utf-8'))


def load_with_legacy_fallback(path: Path, legacy_path: Path, fallback: Any):
    if path.exists():
        return load_json(path, fallback)
    if legacy_path.exists():
        return load_json(legacy_path, fallback)
    return fallback


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def load_state() -> dict[str, Any]:
    return load_with_legacy_fallback(EXECUTION_STATE_PATH, LEGACY_DASHBOARD_STATE_ROOT / 'tradier_execution_state.json', default_state())


def validate_execution_state(state: dict[str, Any]) -> None:
    for intent in state.get('intents', []):
        validate_persisted_intent_lifecycle(intent)
        validate_execution_contract_combinations({
            'lifecycle': {
                'status': intent['status'],
                'history_count': len(intent.get('transition_history') or []),
                'latest_transition': (intent.get('transition_history') or [None])[-1],
            },
            'decision': intent_decision_for_intent(intent),
            'readiness': intent_readiness_for_intent(intent),
            'outcome': intent_outcome_for_intent(intent),
            'escalation': intent_escalation_for_intent(intent),
            'timing': intent_timing_for_intent(intent),
            'external_reference': intent_external_reference_for_intent(intent),
            'execution_attempt': intent_execution_attempt_for_intent(intent),
            'reconciliation': intent_reconciliation_for_intent(intent),
        })


def save_state(state: dict[str, Any]) -> dict[str, Any]:
    state = dict(state)
    validate_execution_state(state)
    state['updatedAt'] = now_iso()
    save_json(EXECUTION_STATE_PATH, state)
    return state


def append_audit(action: str, actor: str, target_id: str, summary: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = load_with_legacy_fallback(AUDIT_LOG_PATH, LEGACY_DASHBOARD_STATE_ROOT / 'tradier_audit_log.json', {'updatedAt': now_iso(), 'events': []})
    event = {
        'timestamp': now_iso(),
        'actor': actor,
        'action': action,
        'target_id': target_id,
        'summary': summary,
    }
    if extra:
        event['extra'] = extra
    payload['events'].append(event)
    payload['updatedAt'] = now_iso()
    save_json(AUDIT_LOG_PATH, payload)
    return event


def upsert_by_key(items: list[dict[str, Any]], key: str, value: Any, new_item: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    replaced = False
    for item in items:
        if item.get(key) == value:
            out.append(new_item)
            replaced = True
        else:
            out.append(item)
    if not replaced:
        out.append(new_item)
    return out


def transition_persisted_intent(
    state: dict[str, Any],
    intent_id: str,
    to_status: str,
    *,
    actor: str = 'system',
    note: str = '',
) -> tuple[dict[str, Any], dict[str, Any]]:
    persisted_intent = None
    for intent in state.get('intents', []):
        if intent.get('intent_id') == intent_id:
            persisted_intent = dict(intent)
            break
    if persisted_intent is None:
        raise ValueError(f'Intent not found in persisted state: {intent_id}')

    transitioned = transition_intent(persisted_intent, to_status, actor=actor, note=note)
    state = dict(state)
    state['intents'] = upsert_by_key(state.get('intents', []), 'intent_id', intent_id, transitioned)
    return transitioned, state
