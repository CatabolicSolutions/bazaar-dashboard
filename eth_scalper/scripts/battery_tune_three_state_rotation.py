#!/usr/bin/env python3
from __future__ import annotations

import itertools
import json
import math
import os
import statistics
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPLAY = ROOT / 'eth_scalper' / 'scripts' / 'replay_three_state_rotation.py'
SUMMARY = ROOT / 'eth_scalper' / 'out' / 'three_state_replay_summary.json'
OUT = ROOT / 'out' / 'three_state_rotation_battery.json'

GRID = {
    'ENTRY_DISCOUNT_PCT': [0.55, 0.75, 0.95, 1.15],
    'REENTRY_RECOVER_PCT': [0.18, 0.24, 0.30],
    'EXIT_EXTENSION_PCT': [0.40, 0.55, 0.70],
    'STOP_PCT': [0.45, 0.60, 0.75],
    'MAX_HOLD_BARS': [4, 6, 8],
    'COOLDOWN_BARS': [2, 4],
}

ORDER = list(GRID.keys())


def run_one(params: dict) -> dict:
    env = os.environ.copy()
    env.update({k: str(v) for k, v in params.items()})
    proc = subprocess.run(['python3', str(REPLAY)], cwd=str(ROOT), env=env, check=True, capture_output=True, text=True)
    summary = json.loads(SUMMARY.read_text())
    return {
        'params': params,
        'summary': summary,
    }


def all_param_sets():
    for values in itertools.product(*(GRID[k] for k in ORDER)):
        yield dict(zip(ORDER, values))


def objective_key(result: dict):
    s = result['summary']
    return (
        float(s.get('eth_equiv_delta_units') or -999999),
        float(s.get('eth_equiv_return_pct') or -999999),
        float(s.get('total_net_pnl_usd') or -999999),
        float(s.get('win_rate') or 0.0),
    )


def numeric(v):
    try:
        return float(v)
    except Exception:
        return None


def dial_effects(results: list[dict]) -> dict:
    base_scores = [numeric(r['summary'].get('eth_equiv_delta_units')) for r in results]
    base_scores = [x for x in base_scores if x is not None]
    overall_mean = statistics.mean(base_scores) if base_scores else 0.0
    out = {}
    for dial in ORDER:
        per_val = {}
        for val in GRID[dial]:
            vals = [numeric(r['summary'].get('eth_equiv_delta_units')) for r in results if r['params'][dial] == val]
            vals = [x for x in vals if x is not None]
            if not vals:
                continue
            per_val[str(val)] = {
                'mean_delta_units': statistics.mean(vals),
                'lift_vs_overall': statistics.mean(vals) - overall_mean,
                'count': len(vals),
            }
        spreads = [v['mean_delta_units'] for v in per_val.values()]
        out[dial] = {
            'overall_mean_delta_units': overall_mean,
            'value_effects': per_val,
            'r_like_spread': (max(spreads) - min(spreads)) if spreads else 0.0,
            'best_value': max(per_val.items(), key=lambda kv: kv[1]['mean_delta_units'])[0] if per_val else None,
        }
    return out


def main() -> None:
    results = []
    for params in all_param_sets():
        results.append(run_one(params))
    ranked = sorted(results, key=objective_key, reverse=True)
    effects = dial_effects(results)
    dial_ranking = sorted(
        ({'dial': k, **v} for k, v in effects.items()),
        key=lambda x: x['r_like_spread'],
        reverse=True,
    )
    out = {
        'objective': 'eth_equivalent_unit_accumulation',
        'tested': len(results),
        'best': ranked[0] if ranked else None,
        'top10': ranked[:10],
        'dial_effects': effects,
        'dial_ranking': dial_ranking,
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(json.dumps({
        'objective': out['objective'],
        'tested': out['tested'],
        'best': out['best'],
        'dial_ranking': [d['dial'] for d in dial_ranking],
    }, indent=2))


if __name__ == '__main__':
    main()
