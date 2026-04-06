#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSION_DIR = ROOT / 'dashboard' / 'state' / 'field_test'
EVENT_LOG = SESSION_DIR / 'monday_session_events.jsonl'
SUMMARY = SESSION_DIR / 'monday_session_summary.json'


def append_event(payload: dict) -> dict:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        'capturedAt': datetime.now(timezone.utc).isoformat(),
        'eventType': payload.get('eventType'),
        'zone': payload.get('zone'),
        'state': payload.get('state'),
        'selected': payload.get('selected'),
        'metadata': payload.get('metadata', {}),
    }
    with EVENT_LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record) + '\n')

    rows = []
    with EVENT_LOG.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    summary = {
        'updatedAt': datetime.now(timezone.utc).isoformat(),
        'count': len(rows),
        'byEventType': {},
        'lastEvent': rows[-1] if rows else None,
    }
    for row in rows:
        et = row.get('eventType') or 'unknown'
        summary['byEventType'][et] = summary['byEventType'].get(et, 0) + 1
    SUMMARY.write_text(json.dumps(summary, indent=2))
    return {'ok': True, 'record': record, 'summary': summary}
