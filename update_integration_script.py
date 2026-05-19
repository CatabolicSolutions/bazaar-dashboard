#!/usr/bin/env python3
import sys

with open('/home/catabolic_solutions/.openclaw/workspace/apply_live_integration.py', 'r') as f:
    lines = f.readlines()

# Find line where def main(): starts
main_start = -1
for i, line in enumerate(lines):
    if line.strip() == 'def main():':
        main_start = i
        break

if main_start == -1:
    print("Could not find main function")
    sys.exit(1)

# Insert new function before main
new_function = '''def patch_bloc_bot():
    """Add trade journal logging to ETH scalper bot"""
    import os
    import shutil
    path = '/var/www/bazaar/eth_scalper/bot/main.py'
    if not os.path.exists(path):
        print(f"ERROR: {path} not found")
        return False
    # backup
    if os.path.exists(path):
        shutil.copy2(path, path + '.bak')
        print(f"Backed up {path}")
    with open(path, 'r') as f:
        lines = f.readlines()
    
    # 1. Add import after sys.path.insert line
    for i, line in enumerate(lines):
        if 'sys.path.insert' in line:
            indent = len(line) - len(line.lstrip())
            lines.insert(i+1, ' ' * indent + 'from trade_journal import log_trade\\n')
            break
    
    # 2. Find line with risk_manager.record_trade(position.signal, position.size_usd, paper=False)
    for i, line in enumerate(lines):
        if 'risk_manager.record_trade(position.signal, position.size_usd, paper=False)' in line:
            indent = len(line) - len(line.lstrip())
            # Add log_trade after this line
            log_line = ' ' * indent + 'try:\\n'
            log_line += ' ' * indent + '    side = "buy" if position.signal.direction == "long" else "sell"\\n'
            log_line += ' ' * indent + '    quantity = position.size_usd / position.entry_price if position.entry_price else 0\\n'
            log_line += ' ' * indent + '    log_trade("bloc", "WETH", side, quantity, position.entry_price, pnl=None, notes="ETH scalper")\\n'
            log_line += ' ' * indent + 'except Exception as e:\\n'
            log_line += ' ' * indent + '    print(f"Failed to log trade: {e}")\\n'
            lines.insert(i+1, log_line)
            break
    
    with open(path, 'w') as f:
        f.writelines(lines)
    print(f"Patched {path}")
    return True

'''

lines.insert(main_start, new_function)

# Now modify main to call patch_bloc_bot
# Find the line where main calls patch functions
# We'll insert after the call to update_monitoring_js
# Look for "update_monitoring_js()" line
for i in range(main_start, len(lines)):
    if 'update_monitoring_js()' in lines[i]:
        # Insert after this line
        indent = len(lines[i]) - len(lines[i].lstrip())
        lines.insert(i+1, ' ' * indent + '# 7. Patch Bloc bot\\n')
        lines.insert(i+2, ' ' * indent + 'if not patch_bloc_bot():\\n')
        lines.insert(i+3, ' ' * indent + '    success = False\\n')
        break

# Write back
with open('/home/catabolic_solutions/.openclaw/workspace/apply_live_integration_v2.py', 'w') as f:
    f.writelines(lines)

print("Updated script saved to apply_live_integration_v2.py")