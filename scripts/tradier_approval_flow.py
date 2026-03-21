import argparse
import json
from datetime import datetime, date
from pathlib import Path

from tradier_board_utils import score_ticket
from tradier_execution import occ_option_symbol, post_order
from tradier_account import readiness_snapshot

RUNS_DIR = Path.home() / '.openclaw' / 'workspace' / 'out' / 'tradier_runs'
STATE_PATH = Path.home() / '.openclaw' / 'workspace' / 'out' / 'tradier_approval_state.json'

LIVE_POSITION_CHANNEL_ID = '1483580321126416565'
TRADING_DESK_CHANNEL_ID = '1483025184775733319'
RULES_CHANNEL_ID = '1483517457049325892'


def load_state():
    if not STATE_PATH.exists():
        return {'active_candidate': None, 'history': []}
    return json.loads(STATE_PATH.read_text(encoding='utf-8'))


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding='utf-8')


def latest_run():
    runs = sorted(RUNS_DIR.glob('*/run.json'), reverse=True)
    if not runs:
        raise RuntimeError('No archived Tradier runs found')
    with open(runs[0], 'r', encoding='utf-8') as f:
        return json.load(f)


def normalize_contract_text(text: str):
    return ''.join(ch.lower() for ch in text if ch.isalnum())


def contract_key(leader):
    cp = 'C' if leader['option_type'].lower().startswith('c') else 'P'
    strike = float(leader['strike'])
    strike_int = str(int(round(strike)))
    strike_full = f"{strike:.2f}".rstrip('0').rstrip('.')
    return f"{leader['symbol']}{strike_int}{cp}{leader['expiration']}|{leader['symbol']}{strike_full}{cp}{leader['expiration']}"


def select_candidate(contract_hint: str | None):
    run = latest_run()
    leaders = run.get('leaders', [])
    if not leaders:
        raise RuntimeError('Latest run has no leaders')
    if not contract_hint:
        return sorted(leaders, key=score_ticket, reverse=True)[0], run

    hint = normalize_contract_text(contract_hint)
    matches = []
    for leader in leaders:
        key_variants = [normalize_contract_text(k) for k in contract_key(leader).split('|')]
        symbol_match = normalize_contract_text(leader['symbol']) in hint
        if any(hint in key or key in hint for key in key_variants) or symbol_match:
            matches.append(leader)
    if not matches:
        raise RuntimeError(f'No leader matched hint: {contract_hint}')
    matches.sort(key=score_ticket, reverse=True)
    return matches[0], run


def candidate_id(leader):
    return f"{leader['symbol']}-{leader['expiration']}-{leader['option_type']}-{leader['strike']}"


def ensure_not_expired(leader):
    exp = datetime.strptime(leader['expiration'], '%Y-%m-%d').date()
    if exp <= date.today():
        raise RuntimeError(f"Candidate contract is expired or same-day stale for execution: {leader['symbol']} {leader['expiration']}")


def build_execution_card(leader, run):
    cp = 'Call' if leader['option_type'].lower().startswith('c') else 'Put'
    entry_ref = leader.get('mid_price') or leader.get('ask') or leader.get('last_price') or 0.0
    target_1 = round(entry_ref * 1.10, 2) if entry_ref else None
    stop_ref = round(entry_ref * 0.90, 2) if entry_ref else None
    lines = []
    lines.append('**TRADE EXECUTION CARD**')
    lines.append(f"- Source run: `{run['run_id']}` from <#{TRADING_DESK_CHANNEL_ID}>")
    lines.append(f"- Contract: {leader['symbol']} {leader['strike']:.2f} {cp} {leader['expiration']}")
    lines.append(f"- Strategy: {leader['strategy']}")
    lines.append(f"- Underlying reference: {leader.get('underlying_price', 0.0):.2f}")
    lines.append(f"- Bid/Ask: {leader.get('bid', 0.0):.2f}/{leader.get('ask', 0.0):.2f}")
    if entry_ref:
        lines.append(f"- Working entry reference: {entry_ref:.2f}")
    lines.append('- Trigger: only on live confirmation / no blind auto-fire from the board')
    if target_1:
        lines.append(f"- Initial scalp target zone: ~{target_1:.2f} (about +10%)")
    if stop_ref:
        lines.append(f"- Initial risk line: ~{stop_ref:.2f} (about -10%)")
    lines.append('- Invalidation: if underlying structure fails or momentum does not pay quickly')
    lines.append('- Macro alignment: candidate must still make sense versus the morning macro overlay')
    lines.append('- Next command: `/take <contract>` to authorize Alfred entry handling')
    return '\n'.join(lines)


def cmd_card(args):
    leader, run = select_candidate(args.contract)
    print(build_execution_card(leader, run))


def cmd_approve(args):
    leader, run = select_candidate(args.contract)
    ensure_not_expired(leader)
    state = load_state()
    account_ready = readiness_snapshot()
    entry_price = leader.get('mid_price') or leader.get('ask') or leader.get('last_price')
    payload = {
        'class': 'option',
        'symbol': leader['symbol'].upper(),
        'option_symbol': occ_option_symbol(leader['symbol'], leader['expiration'], leader['option_type'], leader['strike']),
        'side': 'buy_to_open' if leader['strategy'] == 'Scalping Buy' else 'sell_to_open',
        'quantity': args.qty,
        'type': args.order_type,
        'duration': args.duration,
        'tag': f"alfred-approve-{candidate_id(leader)}",
    }
    if args.order_type in {'limit', 'stop_limit'}:
        working_price = args.price if args.price is not None else entry_price
        if working_price is None:
            raise RuntimeError('No working price available for preview')
        payload['price'] = round(float(working_price), 2)
    preview = post_order(payload, preview=True)
    state['active_candidate'] = {
        'candidate_id': candidate_id(leader),
        'leader': leader,
        'run_id': run['run_id'],
        'preview_payload': payload,
        'preview_response': preview,
        'account_snapshot': account_ready,
        'approved_at': datetime.now().astimezone().isoformat(),
        'status': 'previewed',
    }
    state['history'].append({'ts': datetime.now().astimezone().isoformat(), 'action': 'approve', 'candidate_id': candidate_id(leader)})
    save_state(state)
    print(json.dumps(state['active_candidate'], indent=2))


def cmd_commit(args):
    state = load_state()
    active = state.get('active_candidate')
    if not active:
        raise RuntimeError('No active approved candidate to commit')
    account_ready = readiness_snapshot()
    if not account_ready.get('ready_for_options_execution'):
        raise RuntimeError('Account not execution-ready: ' + '; '.join(account_ready.get('blockers', [])))
    payload = dict(active['preview_payload'])
    result = post_order(payload, preview=False)
    active['status'] = 'committed'
    active['commit_response'] = result
    active['commit_account_snapshot'] = account_ready
    active['committed_at'] = datetime.now().astimezone().isoformat()
    state['history'].append({'ts': datetime.now().astimezone().isoformat(), 'action': 'commit', 'candidate_id': active['candidate_id']})
    save_state(state)
    print(json.dumps(active, indent=2))


def cmd_take(args):
    leader, run = select_candidate(args.contract)
    ensure_not_expired(leader)
    state = load_state()
    account_ready = readiness_snapshot()
    entry_price = leader.get('mid_price') or leader.get('ask') or leader.get('last_price')
    payload = {
        'class': 'option',
        'symbol': leader['symbol'].upper(),
        'option_symbol': occ_option_symbol(leader['symbol'], leader['expiration'], leader['option_type'], leader['strike']),
        'side': 'buy_to_open' if leader['strategy'] == 'Scalping Buy' else 'sell_to_open',
        'quantity': args.qty,
        'type': args.order_type,
        'duration': args.duration,
        'tag': f"alfred-take-{candidate_id(leader)}",
    }
    if args.order_type in {'limit', 'stop_limit'}:
        working_price = args.price if args.price is not None else entry_price
        if working_price is None:
            raise RuntimeError('No working price available for /take')
        payload['price'] = round(float(working_price), 2)
    preview = post_order(payload, preview=True)
    active = {
        'candidate_id': candidate_id(leader),
        'leader': leader,
        'run_id': run['run_id'],
        'preview_payload': payload,
        'preview_response': preview,
        'account_snapshot': account_ready,
        'take_requested_at': datetime.now().astimezone().isoformat(),
        'status': 'previewed-by-take',
    }
    state['active_candidate'] = active
    state['history'].append({'ts': datetime.now().astimezone().isoformat(), 'action': 'take_preview', 'candidate_id': active['candidate_id']})

    if not account_ready.get('ready_for_options_execution'):
        active['status'] = 'blocked'
        active['blocked_reason'] = '; '.join(account_ready.get('blockers', []))
        save_state(state)
        print(json.dumps(active, indent=2))
        return

    result = post_order(payload, preview=False)
    active['status'] = 'committed-by-take'
    active['commit_response'] = result
    active['commit_account_snapshot'] = account_ready
    active['committed_at'] = datetime.now().astimezone().isoformat()
    state['history'].append({'ts': datetime.now().astimezone().isoformat(), 'action': 'take_commit', 'candidate_id': active['candidate_id']})
    save_state(state)
    print(json.dumps(active, indent=2))


def cmd_reject(args):
    state = load_state()
    active = state.get('active_candidate')
    if active:
        state['history'].append({'ts': datetime.now().astimezone().isoformat(), 'action': 'reject', 'candidate_id': active['candidate_id'], 'reason': args.reason or ''})
    state['active_candidate'] = None
    save_state(state)
    print(json.dumps({'status': 'rejected', 'reason': args.reason or ''}, indent=2))


def cmd_status(args):
    print(json.dumps(load_state(), indent=2))


def main():
    parser = argparse.ArgumentParser(description='Discord-native Tradier approval flow state machine')
    sub = parser.add_subparsers(dest='cmd', required=True)

    card = sub.add_parser('card')
    card.add_argument('--contract')
    card.set_defaults(func=cmd_card)

    approve = sub.add_parser('approve')
    approve.add_argument('--contract')
    approve.add_argument('--qty', type=int, default=1)
    approve.add_argument('--order-type', default='limit', choices=['market', 'limit', 'stop', 'stop_limit'])
    approve.add_argument('--duration', default='day')
    approve.add_argument('--price', type=float)
    approve.set_defaults(func=cmd_approve)

    take = sub.add_parser('take')
    take.add_argument('--contract')
    take.add_argument('--qty', type=int, default=1)
    take.add_argument('--order-type', default='limit', choices=['market', 'limit', 'stop', 'stop_limit'])
    take.add_argument('--duration', default='day')
    take.add_argument('--price', type=float)
    take.set_defaults(func=cmd_take)

    commit = sub.add_parser('commit')
    commit.set_defaults(func=cmd_commit)

    reject = sub.add_parser('reject')
    reject.add_argument('--reason')
    reject.set_defaults(func=cmd_reject)

    status = sub.add_parser('status')
    status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
