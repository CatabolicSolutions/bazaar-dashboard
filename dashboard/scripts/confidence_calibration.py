#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path('/home/catabolic_solutions/.openclaw/workspace')
DECISION_DIR = ROOT / 'dashboard' / 'state' / 'decision_context'
DECISION_LOG = DECISION_DIR / 'decision_context_log.jsonl'
ATTACH_LOG = DECISION_DIR / 'outcome_attachments.jsonl'
CALIBRATION = DECISION_DIR / 'confidence_calibration_summary.json'


def read_jsonl(path: Path):
    if not path.exists():
        return []
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def key_for_decision(record: dict):
    c = record.get('contract', {})
    return f"{record.get('type')}|{record.get('symbol')}|{c.get('option_type')}|{c.get('strike')}|{c.get('expiration')}|{record.get('capturedAt')}"


def band(score):
    if score is None:
        return 'unknown'
    if score >= 8:
        return 'high'
    if score >= 6:
        return 'medium'
    return 'low'


def summarize():
    decisions = read_jsonl(DECISION_LOG)
    attachments = read_jsonl(ATTACH_LOG)
    grouped = defaultdict(list)
    for a in attachments:
        base = a['attachmentKey'].rsplit('|', 1)[0]
        grouped[base].append(a)

    qualified = {'high': defaultdict(int), 'medium': defaultdict(int), 'low': defaultdict(int), 'unknown': defaultdict(int)}
    near_miss = defaultdict(int)
    reason_review = defaultdict(lambda: defaultdict(int))
    rejection_review = defaultdict(lambda: defaultdict(int))

    for d in decisions:
        base = key_for_decision(d)
        related = grouped.get(base, [])
        latest = sorted(related, key=lambda x: x.get('elapsedMinutes', 0))[-1] if related else None
        outcome_state = latest.get('outcome', {}).get('state', 'unresolved') if latest else 'unresolved'

        if d.get('type') == 'qualified_trade':
            score = (d.get('confidence') or {}).get('score')
            b = band(score)
            qualified[b][outcome_state] += 1
            for reason in d.get('qualification_reasons', []):
                reason_review[reason][outcome_state] += 1
        elif d.get('type') == 'near_miss':
            near_miss[outcome_state] += 1
            if latest and latest.get('outcome', {}).get('wouldNowQualify'):
                near_miss['would_now_qualify'] += 1
            for reason in d.get('rejection_reasons', []):
                rejection_review[reason][outcome_state] += 1

    summary = {
        'qualifiedTrades': {k: dict(v) for k, v in qualified.items()},
        'nearMisses': dict(near_miss),
        'qualificationReasonReview': {k: dict(v) for k, v in reason_review.items()},
        'rejectionReasonReview': {k: dict(v) for k, v in rejection_review.items()},
        'sourceCounts': {
            'decisionRecords': len(decisions),
            'outcomeAttachments': len(attachments),
        },
    }
    CALIBRATION.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == '__main__':
    summarize()
