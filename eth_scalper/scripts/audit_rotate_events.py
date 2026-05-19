#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
REPLAY = ROOT / 'eth_scalper' / 'scripts' / 'replay_live_bloc_protocol.py'
SUMMARY = ROOT / 'eth_scalper' / 'out' / 'live_bloc_replay_summary.json'
TRADES = ROOT / 'eth_scalper' / 'out' / 'live_bloc_replay_trades.json'
TRACE = ROOT / 'eth_scalper' / 'out' / 'live_bloc_replay_trace.json'
OUT = ROOT / 'out' / 'rotate_event_audit.json'
MD = ROOT / 'out' / 'rotate_event_audit.md'

PARAMS = {
    'MIN_WETH_ACCUMULATION_PCT':'-0.01',
    'REENTRY_SCORE_THRESHOLD':'0.08',
    'REENTRY_SCORE_ARM_THRESHOLD':'0.03',
    'PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT':'0.00',
    'PAIR_ROTATION_COMMIT_PCT':'0.02',
    'PAIR_ROTATION_HOLD_BARS':'1',
    'PAIR_USDC_EXIT_EDGE_PCT':'0.06',
    'PAIR_CHURN_GUARD_BARS':'1',
    'ROTATE_SIGNAL_MIN_EDGE_PCT':'0.04',
    'ROTATE_SIGNAL_MIN_DEV_PCT':'0.02',
    'ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT':'0.005',
    'ROTATE_SIGNAL_PERSIST_BARS':'1',
    'VOL_MULTIPLIER':'0.72',
    'STOP_LOSS':'1.30',
    'COOLDOWN_BARS':'1',
}
HORIZONS = [3, 6, 12, 24]


def run_replay():
    env = os.environ.copy()
    env.update(PARAMS)
    subprocess.run(['python3', str(REPLAY)], cwd=str(ROOT), env=env, check=True, capture_output=True, text=True)


def future_eth_equiv(rows_by_idx, start_idx, side_after, horizon):
    if start_idx + horizon not in rows_by_idx:
        return None
    start = rows_by_idx[start_idx]
    end = rows_by_idx[start_idx + horizon]
    if side_after == 'ETH':
        return end['eth_price'] / start['eth_price']
    if side_after == 'BTC':
        return end['btc_price'] / start['btc_price']
    return None


def held_eth_equiv(rows_by_idx, start_idx, side_before, horizon):
    if start_idx + horizon not in rows_by_idx:
        return None
    start = rows_by_idx[start_idx]
    end = rows_by_idx[start_idx + horizon]
    if side_before == 'ETH':
        return end['eth_price'] / start['eth_price']
    if side_before == 'BTC':
        return (end['btc_price'] / start['btc_price'])
    return None


def main():
    run_replay()
    summary = json.loads(SUMMARY.read_text())
    trades = json.loads(TRADES.read_text())
    trace = json.loads(TRACE.read_text())
    rows_by_idx = {row['idx']: row for row in trace}
    rotates = [t for t in trades if t['action'] == 'ROTATE']

    audit = []
    for rot in rotates:
        row = rows_by_idx.get(rot['idx'])
        if not row:
            continue
        horizons = {}
        for h in HORIZONS:
            realized = future_eth_equiv(rows_by_idx, rot['idx'], rot['side_after'], h)
            held = held_eth_equiv(rows_by_idx, rot['idx'], rot['side_before'], h)
            if realized is None or held is None or held == 0:
                continue
            win_pct = (realized - held) / held * 100.0
            horizons[str(h)] = win_pct
        audit.append({
            'idx': rot['idx'],
            'ts': rot['ts'],
            'side_before': rot['side_before'],
            'side_after': rot['side_after'],
            'price': rot['price'],
            'hold_state': rot['hold_state'],
            'reentry_score': rot['reentry_score'],
            'rotate_edge_pct': row.get('rotate_edge_pct'),
            'spread_dev_pct': row.get('spread_dev_pct'),
            'spread_move_pct': row.get('rotate_edge_pct'),
            'eth_mom_pct': row.get('eth_mom_pct'),
            'btc_mom_pct': row.get('btc_mom_pct'),
            'rotate_signal': row.get('rotate_signal'),
            'rotate_signal_streak': row.get('rotate_signal_streak'),
            'relative_strength_pct': row.get('relative_strength_pct'),
            'horizons': horizons,
        })

    def collect(h):
        vals = [x['horizons'][str(h)] for x in audit if str(h) in x['horizons']]
        return vals

    summary_h = {}
    for h in HORIZONS:
        vals = collect(h)
        if vals:
            summary_h[str(h)] = {
                'count': len(vals),
                'mean_win_pct': mean(vals),
                'win_rate_pct': sum(1 for v in vals if v > 0) / len(vals) * 100.0,
            }

    good12 = [x for x in audit if x['horizons'].get('12', -999) > 0]
    bad12 = [x for x in audit if x['horizons'].get('12', -999) <= 0]
    compare = {
        'good12_count': len(good12),
        'bad12_count': len(bad12),
        'good12_mean_rotate_edge_pct': mean([x['rotate_edge_pct'] for x in good12]) if good12 else None,
        'bad12_mean_rotate_edge_pct': mean([x['rotate_edge_pct'] for x in bad12]) if bad12 else None,
        'good12_mean_spread_dev_pct': mean([x['spread_dev_pct'] for x in good12]) if good12 else None,
        'bad12_mean_spread_dev_pct': mean([x['spread_dev_pct'] for x in bad12]) if bad12 else None,
        'good12_mean_reentry_score': mean([x['reentry_score'] for x in good12]) if good12 else None,
        'bad12_mean_reentry_score': mean([x['reentry_score'] for x in bad12]) if bad12 else None,
        'good12_mean_streak': mean([x['rotate_signal_streak'] for x in good12]) if good12 else None,
        'bad12_mean_streak': mean([x['rotate_signal_streak'] for x in bad12]) if bad12 else None,
    }

    out = {
        'params': PARAMS,
        'replay_summary': summary,
        'rotate_count': len(rotates),
        'horizon_summary': summary_h,
        'compare_12bar': compare,
        'sample_rotates': audit[:25],
    }
    OUT.write_text(json.dumps(out, indent=2))

    lines = [
        '# Rotate Event Audit',
        '',
        f"Rotate count: {len(rotates)}",
        '',
        '## Horizon summary',
    ]
    for h, s in summary_h.items():
        lines.append(f"- {h} bars: mean {s['mean_win_pct']:.4f}% | win rate {s['win_rate_pct']:.1f}% | n={s['count']}")
    lines += [
        '',
        '## 12-bar winner vs loser comparison',
        f"- good count: {compare['good12_count']}",
        f"- bad count: {compare['bad12_count']}",
        f"- good mean rotate_edge_pct: {compare['good12_mean_rotate_edge_pct']}",
        f"- bad mean rotate_edge_pct: {compare['bad12_mean_rotate_edge_pct']}",
        f"- good mean spread_dev_pct: {compare['good12_mean_spread_dev_pct']}",
        f"- bad mean spread_dev_pct: {compare['bad12_mean_spread_dev_pct']}",
        f"- good mean reentry_score: {compare['good12_mean_reentry_score']}",
        f"- bad mean reentry_score: {compare['bad12_mean_reentry_score']}",
        f"- good mean streak: {compare['good12_mean_streak']}",
        f"- bad mean streak: {compare['bad12_mean_streak']}",
    ]
    MD.write_text('\n'.join(lines) + '\n')
    print(json.dumps(out, indent=2))

if __name__ == '__main__':
    main()
