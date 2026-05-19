from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / 'out' / 'runtime_state' / 'engine_lifecycle_events.jsonl'


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit_event(*, engine: str, trade_id: str | None, stage: str, outcome_type: str, status: str, notes: str | None = None, data: dict[str, Any] | None = None) -> dict[str, Any]:
    event = {
        'event_id': str(uuid.uuid4()),
        'timestamp': _ts(),
        'engine': engine,
        'trade_id': trade_id,
        'stage': stage,
        'outcome_type': outcome_type,
        'status': status,
        'notes': notes,
        'data': data or {},
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(event) + '\n')
    return event
