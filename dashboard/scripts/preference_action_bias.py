#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECISION_DIR = ROOT / 'dashboard' / 'state' / 'decision_context'
SETUP_QUALITY = DECISION_DIR / 'setup_quality_summary.json'
CALIBRATION = DECISION_DIR / 'confidence_calibration_summary.json'
OUT = DECISION_DIR / 'preference_action_bias_summary.json'


def read_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def score_counts(counts: dict) -> int:
    return (
        counts.get('favorable', 0)
        + counts.get('improved', 0)
        - counts.get('unfavorable', 0)
        - counts.get('worsened', 0)
    )


def preference_state(score: int, sample: int):
    if sample < 3:
        return 'neutral', 'Evidence thin — emerging bias only'
    if score >= 2:
        return 'favored', 'Observed pattern currently leans constructive'
    if score == 1:
        return 'neutral', 'Slight positive lean, not yet decisive'
    if score == 0:
        return 'neutral', 'Mixed evidence so far'
    if score <= -2:
        return 'de-emphasized', 'Observed pattern currently leans weak'
    return 'cautious', 'Some weakness observed — approach selectively'


def build():
    sq = read_json(SETUP_QUALITY)
    cc = read_json(CALIBRATION)
    setup_classes = sq.get('setupClasses', {})
    class_conf = sq.get('setupClassByConfidence', {})
    qualification_review = cc.get('qualificationReasonReview', {})
    rejection_review = cc.get('rejectionReasonReview', {})

    preferences = []
    for setup_class, counts in setup_classes.items():
        sample = sum(counts.values())
        score = score_counts(counts)
        state, note = preference_state(score, sample)
        preferences.append({
            'setupClass': setup_class,
            'preference': state,
            'score': score,
            'sample': sample,
            'evidenceNote': note,
            'counts': counts,
            'confidenceBands': class_conf.get(setup_class, {}),
        })

    preferences.sort(key=lambda x: (x['preference'] != 'favored', -x['score']))

    strongest_qualification_reasons = []
    for reason, counts in qualification_review.items():
        strongest_qualification_reasons.append({
            'reason': reason,
            'score': score_counts(counts),
            'counts': counts,
        })
    strongest_qualification_reasons.sort(key=lambda x: x['score'], reverse=True)

    weakest_rejection_reasons = []
    for reason, counts in rejection_review.items():
        weakest_rejection_reasons.append({
            'reason': reason,
            'score': score_counts(counts),
            'counts': counts,
        })
    weakest_rejection_reasons.sort(key=lambda x: x['score'])

    summary = {
        'preferences': preferences,
        'favored': [p for p in preferences if p['preference'] == 'favored'],
        'cautious': [p for p in preferences if p['preference'] == 'cautious'],
        'deEmphasized': [p for p in preferences if p['preference'] == 'de-emphasized'],
        'qualificationReasonSignals': strongest_qualification_reasons[:6],
        'rejectionReasonSignals': weakest_rejection_reasons[:6],
        'operatorSummary': {
            'favoredSetupClass': preferences[0]['setupClass'] if preferences else None,
            'sampleNote': 'Preferences are evidence-grounded but early; not automation-grade.'
        }
    }
    OUT.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == '__main__':
    build()
