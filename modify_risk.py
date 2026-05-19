#!/usr/bin/env python3
import json
import sys

file_path = '/var/www/bazaar/scripts/tradier_risk_controls.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

# Find the line with 'cash_day_trade': {
start = -1
for i, line in enumerate(lines):
    if "'cash_day_trade': {" in line:
        start = i
        break
if start == -1:
    print("cash_day_trade not found")
    sys.exit(1)

# Find end of this dict (look for '},' at same indent level)
indent = len(lines[start]) - len(lines[start].lstrip())
for i in range(start + 1, len(lines)):
    if lines[i].strip().startswith('},') and len(lines[i]) - len(lines[i].lstrip()) == indent:
        end = i
        break
else:
    end = start + 10  # fallback

print(f"Replacing lines {start} to {end}")

new_block = """    'cash_day_trade': {
        'allowed_strategies': {'long_call', 'long_put'},
        'max_qty': 2,
        'max_notional': 200.0,
        'manual_limit_drift_pct': 0.05,
        'require_limit_price': False,
    },"""

lines[start:end+1] = [new_block + '\n']

with open(file_path, 'w') as f:
    f.writelines(lines)

print("Updated cash_day_trade policy")