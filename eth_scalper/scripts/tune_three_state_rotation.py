#!/usr/bin/env python3
from __future__ import annotations

import itertools
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPLAY = ROOT / 'eth_scalper' / 'scripts' / 'replay_three_state_rotation.py'
SUMMARY = ROOT / 'eth_scalper' / 'out' / 'three_state_replay_summary.json'
OUT = ROOT / 'out' / 'three_state_rotation_tuning_5set.json'

# 5 intentionally distinct volatility-capture profiles
PARAM_SETS = [
    {
        'name': 'v1_baseline_tighter',
        'ENTRY_DISCOUNT_PCT': 0.60,
        'REENTRY_RECOVER_PCT': 0.22,
        'EXIT_EXTENSION_PCT': 0.45,
        'STOP_PCT': 0.60,
        'MAX_HOLD_BARS': 6,
        'COOLDOWN_BARS': 3,
    },
    {
        'name': 'v2_deeper_discount',
        'ENTRY_DISCOUNT_PCT': 0.85,
        'REENTRY_RECOVER_PCT': 0.26,
        'EXIT_EXTENSION_PCT': 0.55,
        'STOP_PCT': 0.65,
        'MAX_HOLD_BARS': 6,
        'COOLDOWN_BARS': 3,
    },
    {
        'name': 'v3_fast_capture',
        'ENTRY_DISCOUNT_PCT': 0.55,
        'REENTRY_RECOVER_PCT': 0.20,
        'EXIT_EXTENSION_PCT': 0.35,
        'STOP_PCT': 0.55,
        'MAX_HOLD_BARS': 4,
        'COOLDOWN_BARS': 2,
    },
    {
        'name': 'v4_patience_bias',
        'ENTRY_DISCOUNT_PCT': 0.95,
        'REENTRY_RECOVER_PCT': 0.30,
        'EXIT_EXTENSION_PCT': 0.70,
        'STOP_PCT': 0.70,
        'MAX_HOLD_BARS': 8,
        'COOLDOWN_BARS': 4,
    },
    {
        'name': 'v5_asymmetric_risk',
        'ENTRY_DISCOUNT_PCT': 0.75,
        'REENTRY_RECOVER_PCT': 0.24,
        'EXIT_EXTENSION_PCT': 0.50,
        'STOP_PCT': 0.45,
        'MAX_HOLD_BARS': 5,
        'COOLDOWN_BARS': 3,
    },
]


def run_one(params: dict) -> dict:
    env = os.environ.copy()
    env.update({k: str(v) for k, v in params.items() if k != 'name'})
    subprocess.run(['python3', str(REPLAY)], cwd=str(ROOT), env=env, check=True, capture_output=True, text=True)
    summary = json.loads(SUMMARY.read_text())
    return {
        'name': params['name'],
        'params': params,
        'summary': summary,
    }


def rank_key(item: dict):
    s = item['summary']
    return (
        float(s.get('total_net_pnl_usd') or -999999),
        float(s.get('total_return_pct') or -999999),
        float(s.get('win_rate') or 0),
        -float(s.get('loss_count') or 999999),
    )


def main() -> None:
    results = [run_one(p) for p in PARAM_SETS]
    ranked = sorted(results, key=rank_key, reverse=True)
    out = {
        'tested': len(results),
        'results': results,
        'best': ranked[0] if ranked else None,
        'ranking': [r['name'] for r in ranked],
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(json.dumps({
        'tested': out['tested'],
        'ranking': out['ranking'],
        'best': out['best'],
    }, indent=2))


if __name__ == '__main__':
    main()
