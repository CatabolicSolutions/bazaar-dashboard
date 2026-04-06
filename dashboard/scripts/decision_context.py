from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
DECISION_DIR = ROOT / 'dashboard' / 'state' / 'decision_context'
DECISION_LOG = DECISION_DIR / 'decision_context_log.jsonl'
DECISION_SUMMARY = DECISION_DIR / 'decision_context_summary.json'


def _confidence_score(confidence: str | None) -> int | None:
    if not confidence:
        return None
    try:
        return int(str(confidence).split('/')[0])
    except Exception:
        return None


def _qualification_reasons(leader: dict) -> list[str]:
    reasons = []
    if leader.get('section') == 'directional':
        reasons.extend([
            'Near-ATM delta (0.35-0.80) for directional exposure',
            '7-14 DTE for optimal gamma/theta balance',
            'Tight bid-ask spread for clean entry/exit',
        ])
    else:
        reasons.extend([
            'OTM delta (~0.14) for defined-risk premium',
            'Spread structure limits max loss',
            'Time decay working in your favor',
        ])
    try:
        bid = float(leader.get('bid', 0))
        ask = float(leader.get('ask', 0))
        if bid > 0 and ask > 0:
            spread_pct = ((ask - bid) / ((ask + bid) / 2)) * 100
            if spread_pct < 5:
                reasons.append(f'Tight bid-ask spread ({spread_pct:.1f}%)')
    except Exception:
        pass
    if leader.get('fallback'):
        reasons.append('Fallback expiry - confidence adjusted')
    return reasons


def _risk_factors(leader: dict) -> list[str]:
    risks = ['Momentum confirmation required', 'Hard stop discipline essential']
    if leader.get('section') == 'directional':
        risks.append('Directional risk - wrong way move = loss')
    else:
        risks.append('Assignment risk if ITM at expiry')
    if leader.get('fallback'):
        risks.append('Non-optimal DTE may affect Greeks')
    return risks


def build_qualified_trade_record(leader: dict, snapshot: dict) -> dict:
    return {
        'type': 'qualified_trade',
        'capturedAt': datetime.now(timezone.utc).isoformat(),
        'scanUpdatedAt': snapshot.get('updatedAt'),
        'symbol': leader.get('symbol'),
        'contract': {
            'option_type': leader.get('option_type'),
            'strike': leader.get('strike'),
            'expiration': leader.get('exp'),
            'label': leader.get('label'),
        },
        'strategy': leader.get('section'),
        'confidence': {
            'display': leader.get('confidence'),
            'score': _confidence_score(leader.get('confidence')),
        },
        'qualification_reasons': _qualification_reasons(leader),
        'risk_factors': _risk_factors(leader),
        'metrics': {
            'underlying': leader.get('underlying'),
            'delta': leader.get('delta'),
            'bid': leader.get('bid'),
            'ask': leader.get('ask'),
            'vix': snapshot.get('tradier', {}).get('overview', {}).get('vix'),
        },
        'freshness': {
            'boardUpdatedAt': snapshot.get('systemHealth', {}).get('tradierBoardUpdatedAt'),
            'apiLoaded': snapshot.get('systemHealth', {}).get('tradierApiKeyLoaded'),
        },
    }


def build_near_miss_record(candidate: dict, snapshot: dict) -> dict:
    return {
        'type': 'near_miss',
        'capturedAt': datetime.now(timezone.utc).isoformat(),
        'scanUpdatedAt': snapshot.get('updatedAt'),
        'symbol': candidate.get('symbol'),
        'contract': {
            'option_type': candidate.get('option_type'),
            'strike': candidate.get('strike'),
            'expiration': candidate.get('expiration'),
        },
        'strategy': candidate.get('strategy'),
        'near_miss_score': candidate.get('near_miss_score'),
        'rejection_reasons': candidate.get('rejection_reasons', []),
        'closeness': candidate.get('closeness', []),
        'metrics': {
            'underlying': candidate.get('underlying'),
            'delta': candidate.get('delta'),
            'bid': candidate.get('bid'),
            'ask': candidate.get('ask'),
            'spread_ratio': candidate.get('spread_ratio'),
            'vix': snapshot.get('tradier', {}).get('overview', {}).get('vix'),
        },
        'freshness': {
            'boardUpdatedAt': snapshot.get('systemHealth', {}).get('tradierBoardUpdatedAt'),
            'apiLoaded': snapshot.get('systemHealth', {}).get('tradierApiKeyLoaded'),
        },
    }


def build_no_trade_record(snapshot: dict) -> dict:
    overview = snapshot.get('tradier', {}).get('overview', {})
    return {
        'type': 'no_trade_environment',
        'capturedAt': datetime.now(timezone.utc).isoformat(),
        'scanUpdatedAt': snapshot.get('updatedAt'),
        'leaderCount': overview.get('leaderCount', 0),
        'directionalCount': overview.get('directionalCount', 0),
        'premiumCount': overview.get('premiumCount', 0),
        'nearMissCount': len(snapshot.get('tradier', {}).get('nearMisses', {}).get('candidates', [])),
        'runNotes': snapshot.get('tradier', {}).get('runNotes', []),
        'freshness': {
            'boardUpdatedAt': snapshot.get('systemHealth', {}).get('tradierBoardUpdatedAt'),
            'apiLoaded': snapshot.get('systemHealth', {}).get('tradierApiKeyLoaded'),
        },
    }


def persist_decision_context(snapshot: dict) -> dict:
    DECISION_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    leaders = snapshot.get('tradier', {}).get('leaders', []) or []
    near_misses = snapshot.get('tradier', {}).get('nearMisses', {}).get('candidates', []) or []

    for leader in leaders:
        records.append(build_qualified_trade_record(leader, snapshot))
    for nm in near_misses:
        records.append(build_near_miss_record(nm, snapshot))
    if not leaders:
        records.append(build_no_trade_record(snapshot))

    with DECISION_LOG.open('a', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record) + '\n')

    summary = {
        'updatedAt': datetime.now(timezone.utc).isoformat(),
        'totalLoggedThisRun': len(records),
        'qualifiedTradeCount': len(leaders),
        'nearMissCount': len(near_misses),
        'noTradeEnvironmentLogged': not bool(leaders),
    }
    DECISION_SUMMARY.write_text(json.dumps(summary, indent=2))
    return summary
