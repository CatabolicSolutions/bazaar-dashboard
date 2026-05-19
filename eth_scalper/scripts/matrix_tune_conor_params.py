#!/usr/bin/env python3
"""Matrix tune over Conor's parameter set. Sweeps key variables, ranks by ETH-equiv return."""
import json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPLAY = ROOT / 'eth_scalper' / 'scripts' / 'run_conor_params_7d.py'
OUT = ROOT / 'out' / 'conor_matrix_tune_7d.json'

# Baseline: Conor's exact params from 9:30AM yesterday
BASELINE = {
    'INITIAL_USDC': 150,
    'FEE_FACTOR': 1 - 0.0005,
    'COOLDOWN_BARS': 1,
    'PAIR_ROTATION_COMMIT_PCT': 0.02,
    'PAIR_ROTATION_HOLD_BARS': 2,
    'PAIR_USDC_EXIT_EDGE_PCT': 0.06,
    'PAIR_CHURN_GUARD_BARS': 2,
    'ROTATE_SIGNAL_MIN_EDGE_PCT': 0.06,
    'ROTATE_SIGNAL_MIN_DEV_PCT': 0.03,
    'ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT': 0.01,
    'ROTATE_SIGNAL_PERSIST_BARS': 2,
    'ROTATE_POST_HOLD_BARS': 8,
    'ARM_WAIT_SUPPRESS_DURING_ROTATE': True,
    'ARM_WAIT_MIN_ROTATE_EDGE_PCT': 0.18,
    'REENTRY_SCORE_THRESHOLD': 0.08,
    'REENTRY_SCORE_ARM_THRESHOLD': 0.03,
    'VOL_MULTIPLIER': 0.72,
    'STOP_LOSS': 1.30,
    'MIN_WETH_ACCUMULATION_PCT': -0.01,
    'PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT': 0.00,
    'VOL_FLOOR': 0.12,
    'VOL_CAP': 3.0,
    'PAIR_SPREAD_TRIGGER_PCT': 0.18,
    'PAIR_REVERSAL_TRIGGER_PCT': 0.08,
    'PAIR_ROTATE_MIN_EDGE_PCT': 0.02,
    'PAIR_ROTATE_EXIT_EDGE_PCT': 0.01,
    'ROTATE_SIGNAL_LOOKBACK_BARS': 12,
    'ROTATE_SIGNAL_MOM_BARS': 3,
    'REGIME_VOL_CHAOS_PCT': 6.0,
    'REGIME_VOL_CALM_PCT': 1.5,
    'VOL_FILTER': 0.3,
    'SELL_EXTENSION_MIN_PCT': 0.15,
    'SELL_RETRACE_TRIGGER_PCT': 0.03,
    'SELL_MIN_EXTENSION_EXIT_PCT': 0.75,
    'SELL_ROLLOVER_RETRACE_PCT': 0.10,
    'SELL_EXTENDED_PROFIT_EXIT_PCT': 0.85,
    'MOMENTUM_HOLD_MIN_TICK_PCT': 0.035,
    'MOMENTUM_NEG_TICK_PCT': -0.015,
    'MOMENTUM_FADE_RATIO': 0.55,
    'REENTRY_RECOVER_ABOVE_SELL_PCT': 0.30,
    'REENTRY_PARITY_BAND_PCT': 0.06,
    'REENTRY_FORCE_AFTER_BARS': 180,
    'REENTRY_START_DISCOUNT_PCT': 0.10,
    'REENTRY_END_PREMIUM_PCT': 0.03,
    'DEEP_REENTRY_DISCOUNT_PCT': 1.0,
    'DEEP_REENTRY_MIN_WETH_GAIN_PCT': 0.02,
    'MISSED_REENTRY_RECOVERY_PCT': 0.55,
    'REENTRY_REANALYZE_AFTER_BARS': 120,
    'REENTRY_REANALYZE_VOL_MULTIPLIER': 0.55,
    'REENTRY_REANALYZE_MAX_PREMIUM_PCT': 0.75,
    'TWO_CYCLE_WETH_BONUS_WEIGHT': 0.25,
}

# === SWEEP GRID ===
# For each key param, test a range. Other params at baseline.
SWEEPS = {
    'COOLDOWN_BARS': [2, 4, 6, 8],
    'REENTRY_SCORE_ARM_THRESHOLD': [0.05, 0.10, 0.15, 0.25, 0.35],
    'REENTRY_SCORE_THRESHOLD': [0.12, 0.18, 0.25, 0.35],
    'ROTATE_SIGNAL_MIN_EDGE_PCT': [0.02, 0.04, 0.05],
    'ROTATE_SIGNAL_PERSIST_BARS': [1, 2, 3],
    'PAIR_ROTATION_COMMIT_PCT': [0.01, 0.02, 0.03, 0.04],
    'PAIR_CHURN_GUARD_BARS': [2, 3, 4],
    'ROTATE_POST_HOLD_BARS': [4, 8, 12],
    'VOL_MULTIPLIER': [0.65, 0.72, 0.80, 0.90],
}

def run_one(params: dict, label: str) -> dict:
    """Run replay with env override for PARAMS dict params. Returns summary."""
    env = os.environ.copy()
    # Convert params dict to flat env vars for the replay script
    for k, v in params.items():
        if isinstance(v, bool):
            env[k] = 'true' if v else 'false'
        else:
            env[k] = str(v)
    result = subprocess.run(
        ['python3', str(REPLAY)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    # Read output from the result file
    out_path = ROOT / 'eth_scalper' / 'out' / 'conor_params_7d_result.json'
    try:
        summary = json.loads(out_path.read_text())
    except:
        summary = {
            'results': {'eth_equiv_return_pct': None, 'trade_count': 0, 'buy_count': 0, 'rotate_count': 0, 'sell_count': 0},
            'error': result.stderr[-500:],
        }
    return {'label': label, 'params': params.copy(), 'summary': summary['results'], 'stderr': result.stderr[-300:] if result.stderr else ''}


def add_baseline():
    """Run baseline once."""
    return run_one(BASELINE, 'baseline (conor 9:30am)')


def sweep_param(param_name: str, values: list) -> list:
    """Run a parameter sweep changing one variable at a time."""
    results = []
    for val in values:
        candidate = BASELINE.copy()
        candidate[param_name] = val
        label = f'{param_name}={val}'
        r = run_one(candidate, label)
        results.append(r)
        print(f"  {label}: {r['summary'].get('eth_equiv_return_pct', 'ERR'):.4f}% | trades={r['summary'].get('trade_count', '?')} | rotates={r['summary'].get('rotate_count', '?')}")
    return results


def combined_sweep(sweeps: list):
    """Run combined sweeps of 2-3 params simultaneously."""
    results = []
    for combo in sweeps:
        candidate = BASELINE.copy()
        labels = []
        for k, v in combo.items():
            candidate[k] = v
            labels.append(f'{k}={v}')
        label = ' | '.join(labels)
        r = run_one(candidate, label)
        results.append(r)
        print(f"  {label}: {r['summary'].get('eth_equiv_return_pct', 'ERR'):.4f}% | trades={r['summary'].get('trade_count', '?')} | rotates={r['summary'].get('rotate_count', '?')}")
    return results


def main():
    all_results = {'baseline': None, 'individual_sweeps': {}, 'combined_sweeps': [], 'top5': []}
    
    print("=" * 70)
    print("MATRIX TUNE: Conor's Parameter Set — 7-Day Historical")
    print("=" * 70)
    
    # 1. Baseline
    print("\n[1/3] Running baseline...")
    base = add_baseline()
    all_results['baseline'] = base
    print(f"  BASELINE: {base['summary'].get('eth_equiv_return_pct', 'ERR'):.4f}% | trades={base['summary'].get('trade_count')} | rotates={base['summary'].get('rotate_count')}")
    
    # 2. Individual sweeps
    print("\n[2/3] Individual parameter sweeps...")
    for param, values in SWEEPS.items():
        print(f"\n  --- Sweeping {param} ---")
        results = sweep_param(param, values)
        all_results['individual_sweeps'][param] = results
    
    # 3. Combined sweeps (best single-param changes combined)
    print("\n[3/3] Combined sweeps (best singles combined)...")
    
    # Find top values from individual sweeps
    best_singles = {}
    for param, results in all_results['individual_sweeps'].items():
        valid = [r for r in results if r['summary'].get('eth_equiv_return_pct') is not None]
        if valid:
            best = max(valid, key=lambda r: r['summary']['eth_equiv_return_pct'])
            best_singles[param] = (best['params'][param], best['summary']['eth_equiv_return_pct'])
    
    # Build smart combinations: take top 3 promising variables and combine their best values
    promising = sorted(best_singles.items(), key=lambda x: x[1][1], reverse=True)[:3]
    
    combos = []
    if len(promising) >= 2:
        param_a, (val_a, _) = promising[0]
        param_b, (val_b, _) = promising[1]
        combos.append({param_a: val_a, param_b: val_b})
        if len(promising) >= 3:
            param_c, (val_c, _) = promising[2]
            combos.append({param_a: val_a, param_b: val_b, param_c: val_c})
    
    # Also test the ones I initially proposed
    combos.append({'COOLDOWN_BARS': 4, 'REENTRY_SCORE_ARM_THRESHOLD': 0.25, 'REENTRY_SCORE_THRESHOLD': 0.35, 'ROTATE_SIGNAL_MIN_EDGE_PCT': 0.04})
    combos.append({'COOLDOWN_BARS': 6, 'REENTRY_SCORE_ARM_THRESHOLD': 0.15})
    combos.append({'COOLDOWN_BARS': 4, 'ROTATE_SIGNAL_PERSIST_BARS': 3, 'ROTATE_POST_HOLD_BARS': 12})
    
    all_results['combined_sweeps'] = combined_sweep(combos)
    
    # 4. Rank all results
    print("\n" + "=" * 70)
    print("FINAL RANKING (by ETH-equiv return)")
    print("=" * 70)
    
    all_runs = [all_results['baseline']]
    for param_results in all_results['individual_sweeps'].values():
        all_runs.extend(param_results)
    all_runs.extend(all_results['combined_sweeps'])
    
    valid_runs = [r for r in all_runs if r['summary'].get('eth_equiv_return_pct') is not None]
    ranked = sorted(valid_runs, key=lambda r: r['summary']['eth_equiv_return_pct'], reverse=True)
    all_results['top5'] = ranked[:5]
    
    print(f"  {'Rank':<5} {'Label':<50} {'Return%':<10} {'Trades':<8} {'Rotates':<8} {'Entry_Classes':<30}")
    print(f"  {'-'*110}")
    for i, r in enumerate(ranked[:10]):
        s = r['summary']
        label = r['label'][:48]
        ret = f"{s.get('eth_equiv_return_pct', 0):+.4f}%"
        trades = s.get('trade_count', 0)
        rotates = s.get('rotate_count', 0)
        entry_cls = str(s.get('entry_class_counts', {}))[:28]
        print(f"  {i+1:<5} {label:<50} {ret:<10} {trades:<8} {rotates:<8} {entry_cls:<30}")
    
    # Save
    # Make output serializable
    serializable = {
        'tested': len(all_runs),
        'baseline': {
            'label': all_results['baseline']['label'],
            'summary': all_results['baseline']['summary'],
        },
        'individual_sweeps': {
            param: [{'label': r['label'], 'summary': r['summary'], 'params': {k: v for k, v in r['params'].items() if k in SWEEPS.get(param, [])}}
                    for r in results]
            for param, results in all_results['individual_sweeps'].items()
        },
        'combined_sweeps': [{'label': r['label'], 'summary': r['summary']} for r in all_results['combined_sweeps']],
        'top5': [{'label': r['label'], 'summary': r['summary']} for r in ranked[:5]],
        'all_ranked': [{'label': r['label'], 'summary': r['summary']} for r in ranked],
    }
    OUT.write_text(json.dumps(serializable, indent=2))
    
    print(f"\nFull results: {OUT}")
    print(f"Best param set: {ranked[0]['label']}")
    print(f"Details: {json.dumps(ranked[0]['summary'], indent=2)}")


if __name__ == '__main__':
    main()
