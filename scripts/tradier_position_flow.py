import argparse
import json
import re
from datetime import datetime
from pathlib import Path

POSITIONS_PATH = Path.home() / '.openclaw' / 'workspace' / 'out' / 'tradier_positions.json'
CLOSED_PATH = Path.home() / '.openclaw' / 'workspace' / 'out' / 'tradier_closed_positions.json'
APPROVAL_STATE_PATH = Path.home() / '.openclaw' / 'workspace' / 'out' / 'tradier_approval_state.json'

PATTERN = re.compile(
    r'^\s*/(?P<action>in|out)\s+'
    r'(?P<qty>\d+)\s+'
    r'(?P<symbol>[A-Za-z]+)\s+'
    r'(?P<strike>\d+(?:\.\d+)?)\s*'
    r'(?P<cp>[CPcp]|call|put)\s+'
    r'(?P<expiry>\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})\s*'
    r'(?:@\s*(?P<price>\d+(?:\.\d+)?))?\s*$',
    re.IGNORECASE,
)


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def norm_expiry(expiry: str) -> str:
    expiry = expiry.strip()
    if '-' in expiry:
        return expiry
    m, d, y = expiry.split('/')
    if len(y) == 2:
        y = '20' + y
    return f'{int(y):04d}-{int(m):02d}-{int(d):02d}'


def cp_norm(cp: str) -> str:
    cp = cp.lower()
    return 'call' if cp in {'c', 'call'} else 'put'


def parse_command(text: str):
    m = PATTERN.match(text.strip())
    if not m:
        raise RuntimeError('Command did not match /in or /out expected format')
    data = m.groupdict()
    return {
        'action': data['action'].lower(),
        'quantity': int(data['qty']),
        'symbol': data['symbol'].upper(),
        'strike': float(data['strike']),
        'option_type': cp_norm(data['cp']),
        'expiration': norm_expiry(data['expiry']),
        'price': float(data['price']) if data.get('price') else None,
    }


def position_id(item):
    return f"{item['symbol']}-{item['expiration']}-{item['option_type']}-{item['strike']}"


def find_open_position(positions, item):
    pid = position_id(item)
    for p in positions:
        if p['id'] == pid and p.get('status') == 'open':
            return p
    return None


def maybe_merge_from_approval(item):
    state = load_json(APPROVAL_STATE_PATH, {'active_candidate': None, 'history': []})
    active = state.get('active_candidate')
    if not active:
        return item
    leader = active.get('leader') or {}
    if (
        leader.get('symbol') == item['symbol']
        and float(leader.get('strike', -1)) == float(item['strike'])
        and leader.get('option_type') == item['option_type']
        and leader.get('expiration') == item['expiration']
    ):
        item['approval_candidate_id'] = active.get('candidate_id')
        item['approval_run_id'] = active.get('run_id')
        item['approval_status'] = active.get('status')
    return item


def cmd_parse(args):
    print(json.dumps(parse_command(args.text), indent=2))


def cmd_in(args):
    item = maybe_merge_from_approval(parse_command(args.text))
    if item['action'] != 'in':
        raise RuntimeError('Expected /in command')
    positions = load_json(POSITIONS_PATH, [])
    pid = position_id(item)
    existing = find_open_position(positions, item)
    record = {
        'id': pid,
        'symbol': item['symbol'],
        'expiration': item['expiration'],
        'option_type': item['option_type'],
        'strike': item['strike'],
        'entry_price': item['price'],
        'quantity': item['quantity'],
        'status': 'open',
        'created_at': datetime.now().astimezone().isoformat(),
        'source': 'manual_or_discord_in',
    }
    for key in ['approval_candidate_id', 'approval_run_id', 'approval_status']:
        if key in item:
            record[key] = item[key]
    positions = [p for p in positions if p['id'] != pid or p.get('status') != 'open']
    positions.append(record)
    save_json(POSITIONS_PATH, positions)
    print(json.dumps({'status': 'registered', 'position': record, 'replaced_existing': bool(existing)}, indent=2))


def cmd_out(args):
    item = parse_command(args.text)
    if item['action'] != 'out':
        raise RuntimeError('Expected /out command')
    positions = load_json(POSITIONS_PATH, [])
    closed = load_json(CLOSED_PATH, [])
    open_pos = find_open_position(positions, item)
    if not open_pos:
        raise RuntimeError('No matching open position found for /out command')
    open_pos['status'] = 'closed'
    open_pos['closed_at'] = datetime.now().astimezone().isoformat()
    open_pos['exit_price'] = item['price']
    open_pos['exit_quantity'] = item['quantity']
    if open_pos.get('entry_price') and item.get('price'):
        open_pos['pnl_pct'] = ((item['price'] - open_pos['entry_price']) / open_pos['entry_price']) * 100.0
    closed.append(open_pos)
    positions = [p for p in positions if not (p['id'] == open_pos['id'] and p.get('status') == 'closed')]
    save_json(POSITIONS_PATH, positions)
    save_json(CLOSED_PATH, closed)
    print(json.dumps({'status': 'closed', 'position': open_pos}, indent=2))


def main():
    parser = argparse.ArgumentParser(description='Tradier /in /out parser and position lifecycle bridge')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('parse')
    p.add_argument('--text', required=True)
    p.set_defaults(func=cmd_parse)

    i = sub.add_parser('in')
    i.add_argument('--text', required=True)
    i.set_defaults(func=cmd_in)

    o = sub.add_parser('out')
    o.add_argument('--text', required=True)
    o.set_defaults(func=cmd_out)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
