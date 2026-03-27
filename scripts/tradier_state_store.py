from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradier_execution_models import now_iso, transition_intent

ROOT = Path('/home/catabolic_solutions/.openclaw/workspace/dashboard/state')
EXECUTION_STATE_PATH = ROOT / 'tradier_execution_state.json'
AUDIT_LOG_PATH = ROOT / 'tradier_audit_log.json'


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


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def load_state() -> dict[str, Any]:
    return load_json(EXECUTION_STATE_PATH, default_state())


def save_state(state: dict[str, Any]) -> dict[str, Any]:
    state = dict(state)
    state['updatedAt'] = now_iso()
    save_json(EXECUTION_STATE_PATH, state)
    return state


def append_audit(action: str, actor: str, target_id: str, summary: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = load_json(AUDIT_LOG_PATH, {'updatedAt': now_iso(), 'events': []})
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
