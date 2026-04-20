import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / '.bazaar.env'
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:]
        if '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"\''))

API_BASE = os.getenv('TRADIER_BASE_URL', 'https://api.tradier.com/v1')
API_TOKEN = os.getenv('TRADIER_API_KEY')
ACCOUNT_ID = os.getenv('TRADIER_ACCOUNT_ID') or os.getenv('TRADIER_LIVE_ACCOUNT_ID')
HEADERS = {
    'Authorization': f'Bearer {API_TOKEN}',
    'Accept': 'application/json',
    'Content-Type': 'application/x-www-form-urlencoded',
} if API_TOKEN else {}
AUDIT_PATH = Path.home() / '.openclaw' / 'workspace' / 'out' / 'tradier_execution_audit.jsonl'


class TradierExecutionError(RuntimeError):
    pass


def require_env():
    if not API_TOKEN:
        raise TradierExecutionError('TRADIER_API_KEY not set')
    if not ACCOUNT_ID:
        raise TradierExecutionError('TRADIER_ACCOUNT_ID or TRADIER_LIVE_ACCOUNT_ID not set')


def occ_option_symbol(symbol: str, expiry: str, option_type: str, strike: float) -> str:
    root = symbol.upper().ljust(6).replace(' ', '')
    try:
        dt = datetime.strptime(expiry, '%Y-%m-%d')
    except ValueError:
        dt = datetime.strptime(expiry, '%m/%d/%y')
    yymmdd = dt.strftime('%y%m%d')
    cp = 'C' if option_type.lower().startswith('c') else 'P'
    strike_int = int(round(float(strike) * 1000))
    return f"{root}{yymmdd}{cp}{strike_int:08d}"


def post_order(payload: dict, preview: bool = True):
    require_env()
    payload = dict(payload)
    payload['preview'] = 'true' if preview else 'false'
    url = f'{API_BASE}/accounts/{ACCOUNT_ID}/orders'
    r = requests.post(url, data=urlencode(payload), headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    log_audit('preview' if preview else 'place', payload, data)
    return data


def get_order(order_id: str):
    require_env()
    url = f'{API_BASE}/accounts/{ACCOUNT_ID}/orders/{order_id}'
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    log_audit('status', {'order_id': order_id}, data)
    return data


def list_orders():
    require_env()
    url = f'{API_BASE}/accounts/{ACCOUNT_ID}/orders'
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    log_audit('list_orders', {}, data)
    return data


def cancel_order(order_id: str):
    require_env()
    url = f'{API_BASE}/accounts/{ACCOUNT_ID}/orders/{order_id}'
    r = requests.delete(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    log_audit('cancel', {'order_id': order_id}, data)
    return data


def log_audit(action: str, request_data: dict, response_data: dict):
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps({
            'ts': datetime.now().astimezone().isoformat(),
            'action': action,
            'account_id': ACCOUNT_ID,
            'request': request_data,
            'response': response_data,
        }) + '\n')


def option_payload(args) -> dict:
    option_symbol = args.option_symbol or occ_option_symbol(args.symbol, args.expiry, args.option_type, args.strike)
    payload = {
        'class': 'option',
        'symbol': args.symbol.upper(),
        'option_symbol': option_symbol,
        'side': args.side,
        'quantity': args.qty,
        'type': args.order_type,
        'duration': args.duration,
        'tag': args.tag or 'alfred-tradier',
    }
    if args.price is not None:
        payload['price'] = args.price
    if args.stop is not None:
        payload['stop'] = args.stop
    return payload


def print_json(data):
    print(json.dumps(data, indent=2))


def cmd_preview_option(args):
    payload = option_payload(args)
    print_json(post_order(payload, preview=True))


def cmd_place_option(args):
    payload = option_payload(args)
    if not args.yes:
        raise TradierExecutionError('Live placement requires --yes')
    print_json(post_order(payload, preview=False))


def cmd_status(args):
    print_json(get_order(args.order_id))


def cmd_list(args):
    print_json(list_orders())


def cmd_cancel(args):
    if not args.yes:
        raise TradierExecutionError('Cancel requires --yes')
    print_json(cancel_order(args.order_id))


def main():
    parser = argparse.ArgumentParser(description='Tradier execution foundation for Alfred')
    sub = parser.add_subparsers(dest='cmd', required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--symbol', required=True)
    common.add_argument('--expiry', required=True, help='YYYY-MM-DD or MM/DD/YY')
    common.add_argument('--option-type', required=True, choices=['call', 'put', 'c', 'p'])
    common.add_argument('--strike', required=True, type=float)
    common.add_argument('--qty', required=True, type=int)
    common.add_argument('--side', required=True, choices=['buy_to_open', 'sell_to_close', 'sell_to_open', 'buy_to_close'])
    common.add_argument('--order-type', default='limit', choices=['market', 'limit', 'stop', 'stop_limit'])
    common.add_argument('--duration', default='day')
    common.add_argument('--price', type=float)
    common.add_argument('--stop', type=float)
    common.add_argument('--option-symbol')
    common.add_argument('--tag')

    p1 = sub.add_parser('preview-option', parents=[common])
    p1.set_defaults(func=cmd_preview_option)

    p2 = sub.add_parser('place-option', parents=[common])
    p2.add_argument('--yes', action='store_true')
    p2.set_defaults(func=cmd_place_option)

    st = sub.add_parser('status')
    st.add_argument('--order-id', required=True)
    st.set_defaults(func=cmd_status)

    ls = sub.add_parser('list-orders')
    ls.set_defaults(func=cmd_list)

    cc = sub.add_parser('cancel')
    cc.add_argument('--order-id', required=True)
    cc.add_argument('--yes', action='store_true')
    cc.set_defaults(func=cmd_cancel)

    args = parser.parse_args()
    try:
        args.func(args)
    except TradierExecutionError as e:
        raise SystemExit(str(e))


if __name__ == '__main__':
    main()
