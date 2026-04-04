#!/usr/bin/env python3
import json
import os
from datetime import date, datetime
from pathlib import Path

import requests

TRADIER_API_KEY = os.getenv('TRADIER_API_KEY')
if not TRADIER_API_KEY:
    raise SystemExit('TRADIER_API_KEY environment variable not set')

BASE_URL = 'https://api.tradier.com/v1/markets/'
HEADERS = {
    'Accept': 'application/json',
    'Authorization': f'Bearer {TRADIER_API_KEY}'
}

SYMBOLS = ["SPX", "SPY", "NDX", "QQQ", "NVDA", "TSLA", "XSP", "IWM", "VIX", "AMD", "AAPL"]
TARGET_DTE = [7, 14]
MIN_BID = 0.05
MAX_BID_ASK_SPREAD_RATIO = 0.35
SCALPING_DELTA_RANGES = {0: (0.35, 0.65), 1: (0.50, 0.80)}
CREDIT_DELTA_RANGE = (0.10, 0.18)
SCALPING_DISTANCE_LIMITS = {0: 0.005, 1: 0.05}
OUT = Path.home() / '.openclaw' / 'workspace' / 'dashboard' / 'state' / 'near_miss_candidates.json'


def safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def get_quote(symbol):
    r = requests.get(f'{BASE_URL}quotes', params={'symbols': symbol, 'greeks': 'false'}, headers=HEADERS, timeout=20)
    r.raise_for_status()
    q = r.json().get('quotes', {}).get('quote')
    return q.get('last') if q else None


def get_vix():
    return get_quote('VIX')


def get_expirations(symbol):
    r = requests.get(f'{BASE_URL}options/expirations', params={'symbol': symbol}, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json().get('expirations', {}).get('date', []) or []


def get_chain(symbol, exp_date):
    r = requests.get(f'{BASE_URL}options/chains', params={'symbol': symbol, 'expiration': exp_date.strftime('%Y-%m-%d'), 'greeks': 'true'}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def get_delta(option_data):
    return safe_float((option_data.get('greeks') or {}).get('delta'))


def get_mid(option_data):
    bid = safe_float(option_data.get('bid'))
    ask = safe_float(option_data.get('ask'))
    if bid is None or ask is None:
        return None
    return (bid + ask) / 2.0


def get_spread_ratio(option_data):
    bid = safe_float(option_data.get('bid'))
    ask = safe_float(option_data.get('ask'))
    mid = get_mid(option_data)
    if bid is None or ask is None or mid is None or mid <= 0:
        return None
    return (ask - bid) / mid


def distance_pct(option_data, underlying_price):
    strike = safe_float(option_data.get('strike'))
    if strike is None or not underlying_price:
        return None
    return abs(strike - underlying_price) / underlying_price


def classify_candidate(opt, underlying_price, strategy_type, dte_value):
    reasons = []
    closeness = []
    delta = get_delta(opt)
    bid = safe_float(opt.get('bid'))
    ask = safe_float(opt.get('ask'))
    spread_ratio = get_spread_ratio(opt)
    dist_pct = distance_pct(opt, underlying_price)
    option_type = opt.get('option_type')
    strike = safe_float(opt.get('strike'))

    if delta is None:
        return None

    side_valid = True
    if strategy_type == 'scalping_buy' and dte_value == 1:
        side_valid = (option_type == 'call' and strike <= underlying_price) or (option_type == 'put' and strike >= underlying_price)
    elif strategy_type == 'credit_spread_sell':
        side_valid = (option_type == 'call' and strike > underlying_price) or (option_type == 'put' and strike < underlying_price)
    if not side_valid:
        return None

    if bid is None or ask is None or bid < MIN_BID or ask <= 0 or ask < bid:
        reasons.append('insufficient liquidity / weak bid-ask')
    if spread_ratio is None:
        reasons.append('spread unavailable')
    elif spread_ratio > MAX_BID_ASK_SPREAD_RATIO:
        reasons.append('spread too wide')
        if spread_ratio <= MAX_BID_ASK_SPREAD_RATIO * 1.2:
            closeness.append('spread only marginally too wide')

    if strategy_type == 'scalping_buy':
        low, high = SCALPING_DELTA_RANGES[dte_value]
        abs_delta = abs(delta)
        if not (low <= abs_delta <= high):
            reasons.append('delta outside acceptable range')
            if low * 0.9 <= abs_delta <= high * 1.1:
                closeness.append('delta nearly in scalping band')
        if dist_pct is None or dist_pct > SCALPING_DISTANCE_LIMITS[dte_value]:
            reasons.append('reward/risk / distance outside scalping tolerance')
            if dist_pct is not None and dist_pct <= SCALPING_DISTANCE_LIMITS[dte_value] * 1.25:
                closeness.append('distance only slightly outside limit')
    else:
        low, high = CREDIT_DELTA_RANGE
        abs_delta = abs(delta)
        if not (low <= abs_delta <= high):
            reasons.append('delta outside acceptable range')
            if low * 0.85 <= abs_delta <= high * 1.15:
                closeness.append('delta nearly in premium band')

    if not reasons:
        return None

    base_score = 100
    penalties = {
        'spread too wide': 20,
        'insufficient liquidity / weak bid-ask': 25,
        'spread unavailable': 20,
        'delta outside acceptable range': 18,
        'reward/risk / distance outside scalping tolerance': 16,
    }
    for r in reasons:
        base_score -= penalties.get(r, 12)
    near_miss_score = max(base_score, 1)

    if len(reasons) == 1:
        closeness.insert(0, 'one rule away from qualifying')

    return {
        'symbol': opt.get('symbol'),
        'option_type': str(option_type).upper(),
        'strike': safe_float(opt.get('strike'), 0.0),
        'expiration': opt.get('expiration_date'),
        'strategy': 'Directional / Scalping' if strategy_type == 'scalping_buy' else 'Premium / Credit',
        'delta': delta,
        'bid': bid,
        'ask': ask,
        'spread_ratio': spread_ratio,
        'underlying': underlying_price,
        'rejection_reasons': reasons,
        'closeness': closeness[:3],
        'near_miss_score': near_miss_score,
    }


def expiration_selection(symbol, today, dte_target):
    exps = []
    for exp_str in get_expirations(symbol):
        try:
            d = datetime.strptime(exp_str, '%Y-%m-%d').date()
            if d >= today:
                exps.append(d)
        except ValueError:
            pass
    exps.sort()
    if not exps:
        return None
    target = today.fromordinal(today.toordinal() + dte_target)
    exact = next((e for e in exps if e == target), None)
    if exact:
        return exact, False
    fallback = next((e for e in exps if e >= target), exps[-1])
    return fallback, True


def main():
    today = date.today()
    candidates = []
    current_vix = get_vix()
    for symbol in SYMBOLS:
        try:
            underlying = get_quote(symbol)
        except Exception:
            continue
        if not underlying:
            continue
        seen = set()
        for requested_dte in TARGET_DTE:
            sel = expiration_selection(symbol, today, requested_dte)
            if not sel:
                continue
            exp_date, _ = sel
            if exp_date in seen:
                continue
            seen.add(exp_date)
            try:
                chain = get_chain(symbol, exp_date)
            except Exception:
                continue
            options = chain.get('options', {}).get('option', []) or []
            for opt in options:
                for strategy_type in ('scalping_buy', 'credit_spread_sell'):
                    item = classify_candidate(opt, underlying, strategy_type, min((exp_date - today).days, 1))
                    if item:
                        if current_vix and current_vix > 30:
                            item['rejection_reasons'].append('volatility regime mismatch')
                        candidates.append(item)
    candidates.sort(key=lambda x: x['near_miss_score'], reverse=True)
    out = {
        'updatedAt': datetime.utcnow().isoformat() + 'Z',
        'count': len(candidates),
        'candidates': candidates[:8],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(str(OUT))

if __name__ == '__main__':
    main()
