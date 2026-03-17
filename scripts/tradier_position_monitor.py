import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = 'https://api.tradier.com/v1/markets/'
TRADIER_API_KEY = os.getenv('TRADIER_API_KEY')
HEADERS = {
    'Accept': 'application/json',
    'Authorization': f'Bearer {TRADIER_API_KEY}'
} if TRADIER_API_KEY else {}
POSITIONS_PATH = Path.home() / '.openclaw' / 'workspace' / 'out' / 'tradier_positions.json'


def load_positions():
    if not POSITIONS_PATH.exists():
        return []
    return json.loads(POSITIONS_PATH.read_text(encoding='utf-8'))


def save_positions(data):
    POSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    POSITIONS_PATH.write_text(json.dumps(data, indent=2), encoding='utf-8')


def get_underlying_quote(symbol: str):
    url = f'{BASE_URL}quotes'
    params = {'symbols': symbol, 'greeks': 'false'}
    response = requests.get(url, params=params, headers=HEADERS, timeout=20)
    response.raise_for_status()
    quote = response.json().get('quotes', {}).get('quote')
    if not quote:
        raise RuntimeError(f'No quote found for {symbol}')
    return quote


def get_option_chain(symbol: str, expiration: str):
    url = f'{BASE_URL}options/chains'
    params = {'symbol': symbol, 'expiration': expiration, 'greeks': 'true'}
    response = requests.get(url, params=params, headers=HEADERS, timeout=20)
    response.raise_for_status()
    options = response.json().get('options', {}).get('option')
    if not options:
        raise RuntimeError(f'No option chain found for {symbol} {expiration}')
    return options


def match_contract(options, option_type: str, strike: float):
    for opt in options:
        try:
            if opt.get('option_type', '').lower() == option_type.lower() and float(opt.get('strike')) == float(strike):
                return opt
        except Exception:
            continue
    return None


def mid_price(opt):
    bid = opt.get('bid')
    ask = opt.get('ask')
    if bid is None or ask is None:
        return None
    try:
        return round((float(bid) + float(ask)) / 2.0, 4)
    except Exception:
        return None


def pct_change(entry, current):
    if entry in (None, 0) or current is None:
        return None
    return ((current - entry) / entry) * 100.0


def summarize(position, quote, opt):
    underlying_last = float(quote.get('last'))
    option_mid = mid_price(opt)
    option_last = opt.get('last')
    entry = position.get('entry_price')
    pnl_pct = pct_change(entry, option_mid if option_mid is not None else option_last)
    return {
        'symbol': position['symbol'],
        'expiration': position['expiration'],
        'strike': position['strike'],
        'option_type': position['option_type'],
        'entry_price': entry,
        'quantity': position.get('quantity'),
        'underlying_last': underlying_last,
        'underlying_bid': quote.get('bid'),
        'underlying_ask': quote.get('ask'),
        'option_bid': opt.get('bid'),
        'option_ask': opt.get('ask'),
        'option_last': option_last,
        'option_mid': option_mid,
        'delta': (opt.get('greeks') or {}).get('delta'),
        'open_interest': opt.get('open_interest'),
        'volume': opt.get('volume'),
        'pnl_pct_vs_entry_mid': pnl_pct,
        'timestamp': datetime.now().astimezone().isoformat(),
    }


def status_label(position, snap):
    u = snap['underlying_last']
    soft = position.get('underlying_soft_stop')
    hard = position.get('underlying_hard_stop')
    target = position.get('underlying_target')
    if target is not None and u >= target:
        return 'target-zone'
    if hard is not None and u <= hard:
        return 'hard-stop'
    if soft is not None and u <= soft:
        return 'warning'
    return 'in-play'


def print_snapshot(position, snap):
    status = status_label(position, snap)
    pnl = snap['pnl_pct_vs_entry_mid']
    pnl_str = 'N/A' if pnl is None else f'{pnl:+.2f}%'
    print(f"{position['symbol']} {position['strike']} {position['option_type'].upper()} {position['expiration']} | status={status}")
    print(f"Underlying: {snap['underlying_last']:.2f} (bid {snap['underlying_bid']} / ask {snap['underlying_ask']})")
    print(f"Option: bid {snap['option_bid']} / ask {snap['option_ask']} / last {snap['option_last']} / mid {snap['option_mid']}")
    print(f"Entry: {position['entry_price']:.2f} | PnL vs mid: {pnl_str} | Qty: {position.get('quantity')}")
    print(f"Levels: soft={position.get('underlying_soft_stop')} hard={position.get('underlying_hard_stop')} target={position.get('underlying_target')}")
    print(f"Greeks/flow: delta={snap['delta']} volume={snap['volume']} oi={snap['open_interest']}")
    print(f"Timestamp: {snap['timestamp']}")


def cmd_add(args):
    positions = load_positions()
    position = {
        'id': args.id or f"{args.symbol}-{args.expiration}-{args.option_type}-{args.strike}",
        'symbol': args.symbol.upper(),
        'expiration': args.expiration,
        'option_type': args.option_type.lower(),
        'strike': float(args.strike),
        'entry_price': float(args.entry),
        'quantity': int(args.qty),
        'underlying_soft_stop': args.underlying_soft_stop,
        'underlying_hard_stop': args.underlying_hard_stop,
        'underlying_target': args.underlying_target,
        'created_at': datetime.now().astimezone().isoformat(),
        'notes': args.notes or '',
        'status': 'open',
    }
    positions = [p for p in positions if p['id'] != position['id']]
    positions.append(position)
    save_positions(positions)
    print(json.dumps(position, indent=2))


def cmd_list(_args):
    print(json.dumps(load_positions(), indent=2))


def get_position(position_id):
    for p in load_positions():
        if p['id'] == position_id:
            return p
    raise RuntimeError(f'Position not found: {position_id}')


def fetch_snapshot(position):
    quote = get_underlying_quote(position['symbol'])
    chain = get_option_chain(position['symbol'], position['expiration'])
    opt = match_contract(chain, position['option_type'], position['strike'])
    if not opt:
        raise RuntimeError('Matching option contract not found in chain')
    return summarize(position, quote, opt)


def cmd_snapshot(args):
    position = get_position(args.id)
    snap = fetch_snapshot(position)
    print_snapshot(position, snap)


def cmd_watch(args):
    position = get_position(args.id)
    for i in range(args.iterations):
        snap = fetch_snapshot(position)
        print_snapshot(position, snap)
        if i < args.iterations - 1:
            print('---')
            time.sleep(args.interval)


def main():
    if not TRADIER_API_KEY:
        raise SystemExit('TRADIER_API_KEY not set')

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd', required=True)

    add = sub.add_parser('add')
    add.add_argument('--id')
    add.add_argument('--symbol', required=True)
    add.add_argument('--expiration', required=True)
    add.add_argument('--option-type', required=True, choices=['call', 'put'])
    add.add_argument('--strike', required=True, type=float)
    add.add_argument('--entry', required=True, type=float)
    add.add_argument('--qty', required=True, type=int)
    add.add_argument('--underlying-soft-stop', type=float)
    add.add_argument('--underlying-hard-stop', type=float)
    add.add_argument('--underlying-target', type=float)
    add.add_argument('--notes')
    add.set_defaults(func=cmd_add)

    ls = sub.add_parser('list')
    ls.set_defaults(func=cmd_list)

    snap = sub.add_parser('snapshot')
    snap.add_argument('--id', required=True)
    snap.set_defaults(func=cmd_snapshot)

    watch = sub.add_parser('watch')
    watch.add_argument('--id', required=True)
    watch.add_argument('--interval', type=int, default=30)
    watch.add_argument('--iterations', type=int, default=5)
    watch.set_defaults(func=cmd_watch)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
