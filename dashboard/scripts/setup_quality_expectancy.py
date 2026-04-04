#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path('/home/catabolic_solutions/.openclaw/workspace')
DECISION_DIR = ROOT / 'dashboard' / 'state' / 'decision_context'
DECISION_LOG = DECISION_DIR / 'decision_context_log.jsonl'
ATTACH_LOG = DECISION_DIR / 'outcome_attachments.jsonl'
OUT = DECISION_DIR / 'setup_quality_summary.json'


def read_jsonl(path: Path):
    if not path.exists():
        return []
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def decision_key(d: dict):
    c = d.get('contract', {})
    return f"{d.get('type')}|{d.get('symbol')}|{c.get('option_type')}|{c.get('strike')}|{c.get('expiration')}|{d.get('capturedAt')}"


def confidence_band(score):
    if score is None:
        return 'unknown'
    if score >= 8:
        return 'high'
    if score >= 6:
        return 'medium'
    return 'low'


def setup_class(d: dict):
    strategy = d.get('strategy')
    if strategy in ('directional', 'Directional / Scalping'):
        return 'directional_momentum'
    if strategy in ('premium', 'premium_credit', 'Premium / Credit'):
        return 'premium_credit'
    if 'gap' in json.dumps(d).lower():
        return 'gap_based'
    return 'other'


def summarize():
    decisions = read_jsonl(DECISION_LOG)
    attachments = read_jsonl(ATTACH_LOG)
    grouped = defaultdict(list)
    for a in attachments:
        grouped[a['attachmentKey'].rsplit('|', 1)[0]].append(a)

    by_class = defaultdict(lambda: defaultdict(int))
    by_class_conf = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    qual_reason_quality = defaultdict(lambda: defaultdict(int))
    reject_reason_quality = defaultdict(lambda: defaultdict(int))

    for d in decisions:
        if d.get('type') not in ('qualified_trade', 'near_miss'):
            continue
        latest = None
        rel = grouped.get(decision_key(d), [])
        if rel:
            latest = sorted(rel, key=lambda x: x.get('elapsedMinutes', 0))[-1]
        state = latest.get('outcome', {}).get('state', 'unresolved') if latest else 'unresolved'
        sclass = setup_class(d)
        by_class[sclass][state] += 1

        score = (d.get('confidence') or {}).get('score') if d.get('type') == 'qualified_trade' else d.get('near_miss_score')
        band = confidence_band(score if isinstance(score, int) else None)
        by_class_conf[sclass][band][state] += 1

        for reason in d.get('qualification_reasons', []):
            qual_reason_quality[reason][state] += 1
        for reason in d.get('rejection_reasons', []):
            reject_reason_quality[reason][state] += 1

    def score_bucket(bucket):
        return bucket.get('favorable', 0) + bucket.get('improved', 0) - bucket.get('unfavorable', 0) - bucket.get('worsened', 0)

    ranking = []
    for sclass, counts in by_class.items():
        ranking.append({'setupClass': sclass, 'score': score_bucket(counts), 'counts': dict(counts)})
    ranking.sort(key=lambda x: x['score'], reverse=True)

    out = {
        'setupClasses': {k: dict(v) for k, v in by_class.items()},
        'setupClassByConfidence': {k: {b: dict(v2) for b, v2 in v.items()} for k, v in by_class_conf.items()},
        'qualificationReasonQuality': {k: dict(v) for k, v in qual_reason_quality.items()},
        'rejectionReasonQuality': {k: dict(v) for k, v in reject_reason_quality.items()},
        'ranking': ranking,
        'sampleSize': {
            'decisions': len(decisions),
            'attachments': len(attachments),
            'note': 'Early pattern ranking only; not statistically mature.'
        }
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(json.dumps(out))


if __name__ == '__main__':
    summarize()
