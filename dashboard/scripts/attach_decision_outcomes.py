#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
DECISION_DIR = ROOT / 'dashboard' / 'state' / 'decision_context'
DECISION_LOG = DECISION_DIR / 'decision_context_log.jsonl'
ATTACH_LOG = DECISION_DIR / 'outcome_attachments.jsonl'
ATTACH_SUMMARY = DECISION_DIR / 'outcome_attachment_summary.json'

TRADIER_API_KEY = os.getenv('TRADIER_API_KEY')
BASE_URL = 'https://api.tradier.com/v1/markets/'
HEADERS = {
    'Accept': 'application/json',
    'Authorization': f'Bearer {TRADIER_API_KEY}'
} if TRADIER_API_KEY else None

HORIZONS = {
    'short': timedelta(minutes=30),
    'medium': timedelta(hours=2),
    'later': timedelta(days=1),
}


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


def dt(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except Exception:
        return None


def quote(symbol: str):
    r = requests.get(f'{BASE_URL}quotes', params={'symbols': symbol, 'greeks': 'false'}, headers=HEADERS, timeout=20)
    r.raise_for_status()
    q = r.json().get('quotes', {}).get('quote')
    return q or {}


def option_mark(symbol: str, expiration: str, option_type: str, strike):
    try:
        r = requests.get(f'{BASE_URL}options/chains', params={'symbol': symbol, 'expiration': expiration, 'greeks': 'true'}, headers=HEADERS, timeout=30)
        r.raise_for_status()
        options = r.json().get('options', {}).get('option', []) or []
        for opt in options:
            if str(opt.get('option_type', '')).upper() == str(option_type).upper() and float(opt.get('strike', 0)) == float(strike):
                bid = float(opt.get('bid', 0) or 0)
                ask = float(opt.get('ask', 0) or 0)
                last = opt.get('last')
                mid = ((bid + ask) / 2.0) if bid and ask else last
                return {'bid': bid, 'ask': ask, 'last': last, 'mid': mid}
    except Exception:
        return None
    return None


def attachment_key(record: dict, horizon: str):
    c = record.get('contract', {})
    return f"{record.get('type')}|{record.get('symbol')}|{c.get('option_type')}|{c.get('strike')}|{c.get('expiration')}|{record.get('capturedAt')}|{horizon}"


def later_state(record: dict, underlying_now: float | None, option_now: dict | None):
    metrics = record.get('metrics', {})
    underlying_then = metrics.get('underlying')
    delta = metrics.get('delta')
    if underlying_then is None or underlying_now is None:
        return 'unresolved'
    implied_dir = 'up' if (delta or 0) > 0 else 'down'
    moved_up = underlying_now > float(underlying_then)
    favorable = (implied_dir == 'up' and moved_up) or (implied_dir == 'down' and not moved_up)
    if record.get('type') == 'near_miss' and option_now and option_now.get('mid') is not None:
        spread_ratio = metrics.get('spread_ratio')
        if spread_ratio and spread_ratio > 0.35 and option_now.get('mid'):
            return 'improved' if favorable else 'worsened'
    if record.get('type') == 'qualified_trade':
        return 'favorable' if favorable else 'unfavorable'
    return 'mixed' if favorable else 'worsened'


def attach():
    if not TRADIER_API_KEY:
        raise SystemExit('TRADIER_API_KEY environment variable not set')
    records = read_jsonl(DECISION_LOG)
    existing = {row['attachmentKey'] for row in read_jsonl(ATTACH_LOG)} if ATTACH_LOG.exists() else set()
    now = datetime.now(timezone.utc)
    new_rows = []

    for record in records:
        captured = dt(record.get('capturedAt'))
        if not captured:
            continue
        elapsed = now - captured
        for horizon, threshold in HORIZONS.items():
            if elapsed < threshold:
                continue
            key = attachment_key(record, horizon)
            if key in existing:
                continue
            symbol = record.get('symbol')
            contract = record.get('contract', {})
            q = quote(symbol)
            underlying_now = q.get('last')
            option_now = None
            if contract.get('expiration') and contract.get('option_type') and contract.get('strike') is not None:
                option_now = option_mark(symbol, contract.get('expiration'), contract.get('option_type'), contract.get('strike'))
            row = {
                'attachmentKey': key,
                'decisionType': record.get('type'),
                'capturedAt': record.get('capturedAt'),
                'attachedAt': now.isoformat(),
                'horizon': horizon,
                'elapsedMinutes': round(elapsed.total_seconds() / 60.0, 1),
                'symbol': symbol,
                'contract': contract,
                'outcome': {
                    'underlyingThen': record.get('metrics', {}).get('underlying'),
                    'underlyingNow': underlying_now,
                    'underlyingMove': (underlying_now - float(record.get('metrics', {}).get('underlying'))) if underlying_now is not None and record.get('metrics', {}).get('underlying') is not None else None,
                    'optionNow': option_now,
                    'state': later_state(record, underlying_now, option_now),
                    'wouldNowQualify': None if record.get('type') != 'near_miss' else (later_state(record, underlying_now, option_now) == 'improved'),
                },
            }
            new_rows.append(row)
            existing.add(key)

    DECISION_DIR.mkdir(parents=True, exist_ok=True)
    if new_rows:
        with ATTACH_LOG.open('a') as f:
            for row in new_rows:
                f.write(json.dumps(row) + '\n')
    summary = {
        'updatedAt': now.isoformat(),
        'newAttachments': len(new_rows),
        'totalAttachments': len(read_jsonl(ATTACH_LOG)) if ATTACH_LOG.exists() else len(new_rows),
        'horizons': list(HORIZONS.keys()),
    }
    ATTACH_SUMMARY.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == '__main__':
    attach()
