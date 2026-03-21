import argparse
import json
from datetime import datetime
from pathlib import Path

from tradier_position_monitor import fetch_snapshot, load_positions

POLICY_PATH = Path.home() / '.openclaw' / 'workspace' / 'out' / 'tradier_exit_policies.json'


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def get_open_position(position_id):
    positions = load_positions()
    for p in positions:
        if p['id'] == position_id and p.get('status') == 'open':
            return p
    raise RuntimeError(f'Open position not found: {position_id}')


def classify(position, snap, policy):
    underlying = snap['underlying_last']
    option_mark = snap['option_mid'] if snap['option_mid'] is not None else snap['option_last']
    out = {
        'state': 'in_play',
        'reasons': [],
    }

    u_hard = policy.get('underlying_hard_stop')
    u_soft = policy.get('underlying_soft_stop')
    u_target = policy.get('underlying_target')
    u_stretch = policy.get('underlying_stretch_target')
    o_hard = policy.get('option_hard_stop')
    o_soft = policy.get('option_soft_stop')
    o_target = policy.get('option_target')
    o_stretch = policy.get('option_stretch_target')

    if u_hard is not None and underlying <= u_hard:
        out['state'] = 'exit_now'
        out['reasons'].append(f'underlying <= hard stop ({underlying:.2f} <= {u_hard:.2f})')
    elif o_hard is not None and option_mark is not None and option_mark <= o_hard:
        out['state'] = 'exit_now'
        out['reasons'].append(f'option <= hard stop ({option_mark:.2f} <= {o_hard:.2f})')
    elif u_target is not None and underlying >= u_target:
        out['state'] = 'target_zone'
        out['reasons'].append(f'underlying >= target ({underlying:.2f} >= {u_target:.2f})')
        if u_stretch is not None and underlying >= u_stretch:
            out['state'] = 'stretch_zone'
            out['reasons'].append(f'underlying >= stretch ({underlying:.2f} >= {u_stretch:.2f})')
    elif o_target is not None and option_mark is not None and option_mark >= o_target:
        out['state'] = 'target_zone'
        out['reasons'].append(f'option >= target ({option_mark:.2f} >= {o_target:.2f})')
        if o_stretch is not None and option_mark >= o_stretch:
            out['state'] = 'stretch_zone'
            out['reasons'].append(f'option >= stretch ({option_mark:.2f} >= {o_stretch:.2f})')
    elif u_soft is not None and underlying <= u_soft:
        out['state'] = 'warning'
        out['reasons'].append(f'underlying <= soft stop ({underlying:.2f} <= {u_soft:.2f})')
    elif o_soft is not None and option_mark is not None and option_mark <= o_soft:
        out['state'] = 'warning'
        out['reasons'].append(f'option <= soft stop ({option_mark:.2f} <= {o_soft:.2f})')

    return out


def cmd_set(args):
    policies = load_json(POLICY_PATH, {})
    policy = {
        'position_id': args.position_id,
        'trade_type': args.trade_type,
        'underlying_soft_stop': args.underlying_soft_stop,
        'underlying_hard_stop': args.underlying_hard_stop,
        'underlying_target': args.underlying_target,
        'underlying_stretch_target': args.underlying_stretch_target,
        'option_soft_stop': args.option_soft_stop,
        'option_hard_stop': args.option_hard_stop,
        'option_target': args.option_target,
        'option_stretch_target': args.option_stretch_target,
        'auto_exit_hard_stop': args.auto_exit_hard_stop,
        'updated_at': datetime.now().astimezone().isoformat(),
    }
    policies[args.position_id] = policy
    save_json(POLICY_PATH, policies)
    print(json.dumps(policy, indent=2))


def cmd_eval(args):
    position = get_open_position(args.position_id)
    policies = load_json(POLICY_PATH, {})
    policy = policies.get(args.position_id)
    if not policy:
        raise RuntimeError(f'No exit policy found for {args.position_id}')
    snap = fetch_snapshot(position)
    result = classify(position, snap, policy)
    print(json.dumps({'position': position, 'snapshot': snap, 'policy': policy, 'evaluation': result}, indent=2))


def main():
    parser = argparse.ArgumentParser(description='Tradier exit policy and monitor evaluation')
    sub = parser.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('set')
    s.add_argument('--position-id', required=True)
    s.add_argument('--trade-type', default='scalp')
    s.add_argument('--underlying-soft-stop', type=float)
    s.add_argument('--underlying-hard-stop', type=float)
    s.add_argument('--underlying-target', type=float)
    s.add_argument('--underlying-stretch-target', type=float)
    s.add_argument('--option-soft-stop', type=float)
    s.add_argument('--option-hard-stop', type=float)
    s.add_argument('--option-target', type=float)
    s.add_argument('--option-stretch-target', type=float)
    s.add_argument('--auto-exit-hard-stop', action='store_true')
    s.set_defaults(func=cmd_set)

    e = sub.add_parser('eval')
    e.add_argument('--position-id', required=True)
    e.set_defaults(func=cmd_eval)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
