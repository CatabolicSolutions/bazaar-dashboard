#!/usr/bin/env python3
"""Wind-tunnel backtest for reversal/continuation ETH scalp logic."""
import json
import math
import itertools
from pathlib import Path
from statistics import mean, median

DATA_PATH = Path('/home/catabolic_solutions/.openclaw/workspace/eth_scalper/out_eth_market_chart_30d.json')


def pct(a, b):
    return ((b - a) / a * 100.0) if a else 0.0


def load_rows():
    data = json.loads(DATA_PATH.read_text())
    prices = data['prices']
    vols = data.get('total_volumes', [])
    mcap = data.get('market_caps', [])
    rows = []
    for i, (ts, price) in enumerate(prices):
        volume = vols[i][1] if i < len(vols) else None
        market_cap = mcap[i][1] if i < len(mcap) else None
        rows.append({'ts': ts / 1000.0, 'price': float(price), 'volume': float(volume or 0.0), 'market_cap': float(market_cap or 0.0)})
    return rows


def enrich(rows):
    for i, row in enumerate(rows):
        p = row['price']
        prev = rows[i - 1]['price'] if i >= 1 else p
        prev2 = rows[i - 2]['price'] if i >= 2 else prev
        row['ret_1'] = pct(prev, p) if i >= 1 else 0.0
        row['ret_2'] = pct(prev2, p) if i >= 2 else 0.0
        start = max(0, i - 11)
        window = rows[start:i + 1]
        prices = [r['price'] for r in window]
        vols = [r['volume'] for r in window]
        midpoint = sum(prices) / len(prices)
        row['midpoint'] = midpoint
        row['distance_from_mid_pct'] = pct(midpoint, p)
        row['window_low'] = min(prices)
        row['window_high'] = max(prices)
        row['pullback_depth_pct'] = ((midpoint - row['window_low']) / midpoint * 100.0) if midpoint else 0.0
        row['extension_from_low_pct'] = pct(row['window_low'], p)
        row['extension_from_high_pct'] = pct(p, row['window_high'])
        row['velocity'] = row['ret_1']
        row['acceleration'] = row['ret_1'] - (rows[i - 1]['ret_1'] if i >= 2 else 0.0)
        row['volatility_pct'] = (max(prices) - min(prices)) / midpoint * 100 if midpoint else 0.0
        row['volume_ratio'] = (row['volume'] / (sum(vols) / len(vols))) if vols and sum(vols) else 1.0
        row['market_cap_change_pct'] = pct(rows[i - 1]['market_cap'], row['market_cap']) if i >= 1 and rows[i - 1]['market_cap'] else 0.0
        prev_ret = rows[i - 1]['ret_1'] if i >= 1 else 0.0
        row['reversal_strength_pct'] = abs(prev_ret) + abs(row['ret_1']) if (prev_ret < 0 < row['ret_1']) else 0.0
        row['peak_reversal_strength_pct'] = abs(prev_ret) + abs(row['ret_1']) if (prev_ret > 0 > row['ret_1']) else 0.0
    return rows


def simulate(rows, params):
    trades = []
    i = 12
    while i < len(rows) - 2:
        r = rows[i]
        entry_ok = (
            r['price'] <= r['midpoint'] and
            abs(r['distance_from_mid_pct']) >= params['distance_min'] and
            r['pullback_depth_pct'] >= params['pullback_min'] and
            r['reversal_strength_pct'] >= params['reversal_min'] and
            r['velocity'] > 0 and
            r['volume_ratio'] >= params['volume_ratio_min'] and
            r['volatility_pct'] >= params['volatility_min'] and
            r['acceleration'] >= params['accel_min']
        )
        if not entry_ok:
            i += 1
            continue
        entry = r['price']
        peak = entry
        exit_price = entry
        reason = 'timeout'
        exit_idx = min(len(rows) - 1, i + params['max_hold_bars'])
        for j in range(i + 1, min(len(rows), i + params['max_hold_bars'] + 1)):
            p = rows[j]['price']
            peak = max(peak, p)
            profit_pct = pct(entry, p)
            retrace_pct = pct(peak, p) * -1 if p < peak else 0.0
            if profit_pct <= -params['stop_pct']:
                exit_price = p
                exit_idx = j
                reason = 'stop'
                break
            if profit_pct >= params['target_pct'] and retrace_pct >= params['retrace_pct']:
                exit_price = p
                exit_idx = j
                reason = 'target_retrace'
                break
            if profit_pct >= params['trail_trigger_pct'] and retrace_pct >= params['retrace_pct']:
                exit_price = p
                exit_idx = j
                reason = 'trail_retrace'
                break
            exit_price = p
            exit_idx = j
            reason = 'hold_end'
        gross_pct = pct(entry, exit_price)
        net_pct = gross_pct - params['friction_pct']
        trades.append({
            'entry_idx': i,
            'exit_idx': exit_idx,
            'entry_price': entry,
            'exit_price': exit_price,
            'gross_pct': gross_pct,
            'net_pct': net_pct,
            'reason': reason,
            'hold_bars': exit_idx - i,
            'reversal_strength_pct': r['reversal_strength_pct'],
            'volume_ratio': r['volume_ratio'],
            'volatility_pct': r['volatility_pct'],
        })
        i = exit_idx + 1
    wins = [t for t in trades if t['net_pct'] > 0]
    return {
        'params': params,
        'trade_count': len(trades),
        'win_rate': (len(wins) / len(trades)) if trades else 0.0,
        'avg_net_pct': mean([t['net_pct'] for t in trades]) if trades else 0.0,
        'median_net_pct': median([t['net_pct'] for t in trades]) if trades else 0.0,
        'total_net_pct': sum(t['net_pct'] for t in trades),
        'avg_hold_bars': mean([t['hold_bars'] for t in trades]) if trades else 0.0,
        'sample_trades': trades[:5],
    }


def main():
    import os
    rows = enrich(load_rows())
    fast_mode = os.getenv('FAST_MODE', '0') == '1'
    grid = {
        'distance_min': [0.05, 0.10, 0.15],
        'pullback_min': [0.15, 0.30, 0.50],
        'reversal_min': [0.05, 0.10, 0.15, 0.20],
        'volume_ratio_min': [0.85, 0.95, 1.00],
        'volatility_min': [0.30, 0.50, 0.75],
        'accel_min': [-0.10, 0.00, 0.10],
        'target_pct': [0.20, 0.25, 0.35],
        'stop_pct': [0.25, 0.35, 0.50],
        'trail_trigger_pct': [0.10, 0.15, 0.20],
        'retrace_pct': [0.03, 0.05, 0.07],
        'max_hold_bars': [2, 3, 4, 5, 6],
        'friction_pct': [0.02, 0.04, 0.06],
    }
    if fast_mode:
        grid = {
            'distance_min': [0.05, 0.10],
            'pullback_min': [0.15, 0.30],
            'reversal_min': [0.05, 0.10, 0.15],
            'volume_ratio_min': [0.85, 1.00],
            'volatility_min': [0.30, 0.75],
            'accel_min': [-0.10, 0.00],
            'target_pct': [0.20, 0.25],
            'stop_pct': [0.25, 0.35],
            'trail_trigger_pct': [0.10, 0.15],
            'retrace_pct': [0.03, 0.05],
            'max_hold_bars': [2, 3, 4],
            'friction_pct': [0.02, 0.04, 0.06],
        }
    keys = list(grid.keys())
    results = []
    for vals in itertools.product(*(grid[k] for k in keys)):
        params = dict(zip(keys, vals))
        res = simulate(rows, params)
        if res['trade_count'] >= 8:
            results.append(res)
    results.sort(key=lambda r: (r['avg_net_pct'], r['win_rate'], r['total_net_pct']), reverse=True)
    payload = {
        'rows': len(rows),
        'tested': len(results),
        'top_results': results[:10],
        'best': results[0] if results else None,
    }
    out = Path('/home/catabolic_solutions/.openclaw/workspace/eth_scalper/backtest_results.json')
    out.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))


if __name__ == '__main__':
    main()
