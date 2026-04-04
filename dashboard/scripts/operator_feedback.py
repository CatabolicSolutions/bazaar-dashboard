#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/home/catabolic_solutions/.openclaw/workspace')
FEEDBACK_DIR = ROOT / 'dashboard' / 'state' / 'operator_feedback'
FEEDBACK_LOG = FEEDBACK_DIR / 'feedback_log.jsonl'
FEEDBACK_SUMMARY = FEEDBACK_DIR / 'feedback_summary.json'

VALID_STATES = {'agree', 'disagree', 'watch', 'strong', 'weak', 'useful', 'misleading'}


def append_feedback(payload: dict) -> dict:
    state = payload.get('feedback')
    if state not in VALID_STATES:
        raise ValueError(f'invalid feedback state: {state}')

    record = {
        'capturedAt': datetime.now(timezone.utc).isoformat(),
        'targetType': payload.get('targetType'),
        'feedback': state,
        'symbol': payload.get('symbol'),
        'contract': payload.get('contract', {}),
        'strategy': payload.get('strategy'),
        'decisionRef': payload.get('decisionRef'),
        'snapshotUpdatedAt': payload.get('snapshotUpdatedAt'),
        'metadata': payload.get('metadata', {}),
    }

    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    with FEEDBACK_LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record) + '\n')

    rows = []
    with FEEDBACK_LOG.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    summary = {
        'updatedAt': datetime.now(timezone.utc).isoformat(),
        'count': len(rows),
        'byFeedback': {},
        'byTargetType': {},
    }
    for row in rows:
        summary['byFeedback'][row['feedback']] = summary['byFeedback'].get(row['feedback'], 0) + 1
        tt = row.get('targetType') or 'unknown'
        summary['byTargetType'][tt] = summary['byTargetType'].get(tt, 0) + 1

    FEEDBACK_SUMMARY.write_text(json.dumps(summary, indent=2))
    return {'ok': True, 'record': record, 'summary': summary}
