import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import requests

API_BASE = os.getenv('TRADIER_BASE_URL', 'https://api.tradier.com/v1')
API_TOKEN = os.getenv('TRADIER_API_KEY')
ACCOUNT_ID = os.getenv('TRADIER_ACCOUNT_ID') or os.getenv('TRADIER_LIVE_ACCOUNT_ID')
HEADERS = {
    'Authorization': f'Bearer {API_TOKEN}',
    'Accept': 'application/json',
} if API_TOKEN else {}
STATE_PATH = Path.home() / '.openclaw' / 'workspace' / 'out' / 'tradier_account_state.json'


class TradierAccountError(RuntimeError):
    pass


def require_env():
    if not API_TOKEN:
        raise TradierAccountError('TRADIER_API_KEY not set')
    if not ACCOUNT_ID:
        raise TradierAccountError('TRADIER_ACCOUNT_ID or TRADIER_LIVE_ACCOUNT_ID not set')


def get(path: str):
    require_env()
    url = f'{API_BASE}{path}'
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def profile():
    return get('/user/profile')


def balances():
    return get(f'/accounts/{ACCOUNT_ID}/balances')


def positions():
    return get(f'/accounts/{ACCOUNT_ID}/positions')


def readiness_snapshot():
    p = profile()['profile']
    b = balances()['balances']
    margin = b.get('margin') or {}
    option_bp = float(margin.get('option_buying_power') or 0.0)
    stock_bp = float(margin.get('stock_buying_power') or 0.0)
    uncleared = float(b.get('uncleared_funds') or 0.0)
    total_cash = float(b.get('total_cash') or 0.0)
    option_level = p['account'].get('option_level')
    status = (p['account'].get('status') or '').lower()

    blockers = []
    warnings = []
    ready = True

    if status != 'active':
        ready = False
        blockers.append(f'account status is {status}, not active')
    if option_level is None or int(option_level) < 1:
        ready = False
        blockers.append('option approval level missing/inadequate')
    if option_bp <= 0:
        ready = False
        blockers.append('option buying power is zero')
    if uncleared > 0:
        warnings.append(f'uncleared funds present: {uncleared:.2f}')

    snapshot = {
        'checked_at': datetime.now().astimezone().isoformat(),
        'account_id': ACCOUNT_ID,
        'account_status': status,
        'option_level': option_level,
        'total_cash': total_cash,
        'uncleared_funds': uncleared,
        'option_buying_power': option_bp,
        'stock_buying_power': stock_bp,
        'ready_for_options_execution': ready,
        'blockers': blockers,
        'warnings': warnings,
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
    return snapshot


def print_json(data):
    print(json.dumps(data, indent=2))


def cmd_profile(_):
    print_json(profile())


def cmd_balances(_):
    print_json(balances())


def cmd_positions(_):
    print_json(positions())


def cmd_ready(_):
    print_json(readiness_snapshot())


def main():
    parser = argparse.ArgumentParser(description='Tradier account state / readiness checks')
    sub = parser.add_subparsers(dest='cmd', required=True)
    for name, func in [('profile', cmd_profile), ('balances', cmd_balances), ('positions', cmd_positions), ('ready', cmd_ready)]:
        p = sub.add_parser(name)
        p.set_defaults(func=func)
    args = parser.parse_args()
    try:
        args.func(args)
    except TradierAccountError as e:
        raise SystemExit(str(e))


if __name__ == '__main__':
    main()
