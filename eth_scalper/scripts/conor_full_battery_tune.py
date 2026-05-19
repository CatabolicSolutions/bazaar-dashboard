#!/usr/bin/env python3
"""
FULL BATTERY: Conor's parameter set — systematic sweep across ALL decision-relevant variables.

Phase 1: Rotate signal detection (the +1.21% lever — but there's more)
Phase 2: Entry gating (pair_entry_ok — the REAL arm_wait gate)
Phase 3: Exit/hold parameters
Phase 4: Combined best-of-class
"""
import json, os, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPLAY = ROOT / 'eth_scalper' / 'scripts' / 'run_conor_params_7d.py'
OUT = ROOT / 'out' / 'conor_full_battery_tune.json'

# === SWEEP GRID — targeting every actual control variable ===

# Phase 1: Rotate signal detection (4 untested vars + persist already known)
PHASE1 = {
    'ROTATE_SIGNAL_MIN_DEV_PCT': [0.01, 0.02, 0.03, 0.04, 0.06],
    'ROTATE_SIGNAL_MIN_SPREAD_MOVE_PCT': [0.005, 0.01, 0.02, 0.03],
    'ROTATE_SIGNAL_MIN_EDGE_PCT': [0.02, 0.04, 0.06, 0.08, 0.10, 0.12],
    'ROTATE_SIGNAL_MOM_BARS': [2, 3, 5, 8],
    'ROTATE_SIGNAL_LOOKBACK_BARS': [8, 12, 24],
    'ROTATE_SIGNAL_PERSIST_BARS': [1, 2, 3],
}

# Phase 2: Entry gating (pair_entry_ok = the REAL arm_wait control)
PHASE2 = {
    'PAIR_SPREAD_TRIGGER_PCT': [0.10, 0.18, 0.25, 0.35, 0.50],
    'PAIR_REVERSAL_TRIGGER_PCT': [0.04, 0.08, 0.12, 0.20],
    'PAIR_ENTRY_MIN_RELATIVE_STRENGTH_PCT': [0.00, 0.05, 0.10, 0.20, 0.30],
    'ARM_WAIT_MIN_ROTATE_EDGE_PCT': [0.05, 0.10, 0.18, 0.25, 0.35],
    'PAIR_ROTATION_COMMIT_PCT': [0.01, 0.02, 0.04],
}

# Phase 3: Exit/hold/vol parameters
PHASE3 = {
    'SELL_EXTENSION_MIN_PCT': [0.08, 0.15, 0.25],
    'SELL_ROLLOVER_RETRACE_PCT': [0.05, 0.10, 0.20],
    'MOMENTUM_FADE_RATIO': [0.40, 0.55, 0.70],
    'VOL_FLOOR': [0.08, 0.10, 0.12, 0.15],
    'VOL_CAP': [2.0, 3.0, 5.0],
    'STOP_LOSS': [0.80, 1.00, 1.30, 1.80],
    'COOLDOWN_BARS': [1, 2, 4],
    'PAIR_CHURN_GUARD_BARS': [1, 2, 3],
    'MIN_WETH_ACCUMULATION_PCT': [-0.05, -0.01, 0.00, 0.02],
}

def _format_val(v):
    """Format value for env var."""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, float):
        return str(v)
    return str(v)

def run_one(overrides: dict, label: str) -> dict:
    env = os.environ.copy()
    for k, v in overrides.items():
        env[k] = _format_val(v)
    result = subprocess.run(
        ['python3', str(REPLAY)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    out_path = ROOT / 'eth_scalper' / 'out' / 'conor_params_7d_result.json'
    try:
        summary = json.loads(out_path.read_text())
        summary = summary.get('results', summary)
    except Exception as e:
        summary = {'eth_equiv_return_pct': None, 'trade_count': 0, 'rotate_count': 0,
                    'error': result.stderr[-500:], 'stderr': result.stderr[-200:]}
    return {'label': label, 'overrides': overrides.copy(), 'summary': summary}

def sweep_param(name: str, values: list, label_prefix: str = '') -> list:
    """Sweep a single parameter, keeping all others at baseline (no overrides = baseline)."""
    results = []
    for val in values:
        label = f'{name}={val}'
        r = run_one({name: val}, label)
        results.append(r)
        ret = r['summary'].get('eth_equiv_return_pct')
        trades = r['summary'].get('trade_count', '?')
        rotates = r['summary'].get('rotate_count', '?')
        print(f"  {label:<55} {f'{ret:+.4f}%' if ret is not None else 'ERR':<12} trades={trades:<4} rotates={rotates}")
    return results

def best_from_sweep(results: list) -> tuple:
    """Return (label, return, overrides) of best result."""
    valid = [r for r in results if r['summary'].get('eth_equiv_return_pct') is not None]
    if not valid:
        return None
    best = max(valid, key=lambda r: r['summary']['eth_equiv_return_pct'])
    return (best['label'], best['summary']['eth_equiv_return_pct'], best['overrides'])

def print_header(phase: str):
    print(f"\n{'='*70}")
    print(f"PHASE: {phase}")
    print(f"{'='*70}")

def main():
    # Run baseline first
    print_header("BASELINE (conor 9:30am set)")
    baseline = run_one({}, 'baseline')
    bl_ret = baseline['summary'].get('eth_equiv_return_pct', 'ERR')
    print(f"  baseline: {f'{bl_ret:+.4f}%' if isinstance(bl_ret, float) else bl_ret} | "
          f"trades={baseline['summary'].get('trade_count')} | "
          f"rotates={baseline['summary'].get('rotate_count')}")
    
    all_results = {'phases': {}, 'baseline': baseline, 'top10': []}
    
    # Phase 1: Rotate signal detection
    print_header("PHASE 1: ROTATE SIGNAL DETECTION")
    for param, values in PHASE1.items():
        print(f"\n  --- {param} ---")
        r = sweep_param(param, values)
        all_results['phases'].setdefault('phase1_rotate', {})[param] = r
    
    # Phase 2: Entry gating
    print_header("PHASE 2: ENTRY GATING (pair_entry_ok)")
    for param, values in PHASE2.items():
        print(f"\n  --- {param} ---")
        r = sweep_param(param, values)
        all_results['phases'].setdefault('phase2_entry', {})[param] = r
    
    # Phase 3: Exit/hold/vol
    print_header("PHASE 3: EXIT / HOLD / VOL")
    for param, values in PHASE3.items():
        print(f"\n  --- {param} ---")
        r = sweep_param(param, values)
        all_results['phases'].setdefault('phase3_exit', {})[param] = r
    
    # Phase 4: Combined — best from each phase
    print_header("PHASE 4: COMBINED BEST OF CLASS")
    
    # Collect all best results per param
    best_singles = {}
    for phase, sweeps in all_results['phases'].items():
        for param, results in sweeps.items():
            b = best_from_sweep(results)
            if b:
                label, ret, overrides = b
                best_singles[param] = (overrides[param], ret, overrides)
    
    # Sort by return, take top 5 individual params
    sorted_params = sorted(best_singles.items(), key=lambda x: x[1][1], reverse=True)
    top_params = sorted_params[:5]
    
    print("\nTop individual improvements:")
    for i, (param, (val, ret, _)) in enumerate(top_params):
        print(f"  {i+1}. {param}={val} → {ret:+.4f}%")
    
    # Build smart combos from top params
    combos = []
    
    # Combo 1: top 2 together
    if len(top_params) >= 2:
        combo = {}
        combo_label_parts = []
        for param, (val, _, _) in top_params[:2]:
            combo[param] = val
            combo_label_parts.append(f'{param}={val}')
        combos.append((' + '.join(combo_label_parts), combo))
    
    # Combo 2: top 3 together
    if len(top_params) >= 3:
        combo = {}
        combo_label_parts = []
        for param, (val, _, _) in top_params[:3]:
            combo[param] = val
            combo_label_parts.append(f'{param}={val}')
        combos.append((' + '.join(combo_label_parts), combo))
    
    # Combo 3: top from each phase baked together
    best_rotate = best_from_sweep(all_results['phases'].get('phase1_rotate', {}).get(list(PHASE1.keys())[0], []))
    # Actually, find best per phase
    phase_bests = {}
    for pname, sweep_dict in all_results['phases'].items():
        all_in_phase = []
        for param_res in sweep_dict.values():
            all_in_phase.extend(param_res)
        b = best_from_sweep(all_in_phase)
        if b:
            phase_bests[pname] = b
    
    if len(phase_bests) >= 2:
        combo = {}
        label_parts = []
        for pname, (lb, _, ovr) in phase_bests.items():
            combo.update(ovr)
            label_parts.append(f'{pname}={lb.split("=")[-1] if "=" in lb else lb}')
        combos.append((' | '.join(label_parts), combo))
    
    # Run combos
    combo_results = []
    for label, overrides in combos:
        print(f"\n  Combo: {label}")
        r = run_one(overrides, label)
        combo_results.append(r)
        ret = r['summary'].get('eth_equiv_return_pct')
        trades = r['summary'].get('trade_count', '?')
        rotates = r['summary'].get('rotate_count', '?')
        print(f"    Result: {f'{ret:+.4f}%' if ret is not None else 'ERR'} | trades={trades} | rotates={rotates}")
    
    all_results['combos'] = combo_results
    
    # === FINAL RANKING ===
    print_header("FINAL RANKING (top 15)")
    
    # Collect every run
    every_run = [baseline]
    for phase_sweeps in all_results['phases'].values():
        for param_results in phase_sweeps.values():
            every_run.extend(param_results)
    every_run.extend(combo_results)
    
    valid = [r for r in every_run if r['summary'].get('eth_equiv_return_pct') is not None]
    ranked = sorted(valid, key=lambda r: r['summary']['eth_equiv_return_pct'], reverse=True)
    all_results['top10'] = ranked[:10]
    
    print(f"  {'Rank':<6} {'Label':<60} {'Return%':<10} {'Trades':<8} {'Rotates':<8}")
    print(f"  {'-'*92}")
    for i, r in enumerate(ranked[:15]):
        s = r['summary']
        label = r['label'][:58]
        ret = f"{s.get('eth_equiv_return_pct', 0):+.4f}%"
        trades = s.get('trade_count', 0)
        rotates = s.get('rotate_count', 0)
        print(f"  {i+1:<6} {label:<60} {ret:<10} {trades:<8} {rotates:<8}")
    
    # Save results
    def serialize_result(r):
        return {
            'label': r['label'],
            'overrides': r.get('overrides', {}),
            'summary': r['summary'],
        }
    serializable = {
        'tested': len(valid),
        'baseline': serialize_result(baseline),
        'top10': [serialize_result(r) for r in ranked[:10]],
        'all_ranked': [serialize_result(r) for r in ranked],
    }
    OUT.write_text(json.dumps(serializable, indent=2))
    print(f"\nFull results: {OUT}")

if __name__ == '__main__':
    main()
