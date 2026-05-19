#!/usr/bin/env python3
"""
Fix Tradier pipeline permissions and risk controls.
Must be run as root.
"""
import os
import sys

def update_risk_controls():
    path = '/var/www/bazaar/scripts/tradier_risk_controls.py'
    with open(path, 'r') as f:
        lines = f.readlines()
    # Find cash_day_trade block
    start = -1
    for i, line in enumerate(lines):
        if "'cash_day_trade': {" in line:
            start = i
            break
    if start == -1:
        print("cash_day_trade not found")
        return False
    # Find end of dict
    indent = len(lines[start]) - len(lines[start].lstrip())
    for i in range(start + 1, len(lines)):
        if lines[i].strip().startswith('},') and len(lines[i]) - len(lines[i].lstrip()) == indent:
            end = i
            break
    else:
        end = start + 10
    new_block = """    'cash_day_trade': {
        'allowed_strategies': {'long_call', 'long_put'},
        'max_qty': 2,
        'max_notional': 200.0,
        'manual_limit_drift_pct': 0.05,
        'require_limit_price': False,
    },"""
    lines[start:end+1] = [new_block + '\n']
    with open(path, 'w') as f:
        f.writelines(lines)
    print("Updated cash_day_trade risk policy (max_qty=2, max_notional=200)")
    return True

def fix_runtime_state():
    runtime_dir = '/var/www/bazaar/out/runtime_state'
    if os.path.exists(runtime_dir):
        os.system(f'chown -R alfred-deploy:alfred-deploy {runtime_dir}')
        print(f"Changed ownership of {runtime_dir}")
    else:
        os.makedirs(runtime_dir, exist_ok=True)
        os.system(f'chown -R alfred-deploy:alfred-deploy {runtime_dir}')
        print(f"Created {runtime_dir} and set ownership")
    return True

if __name__ == '__main__':
    if os.geteuid() != 0:
        print("ERROR: This script must be run as root (sudo).")
        sys.exit(1)
    update_risk_controls()
    fix_runtime_state()
    print("All fixes applied.")