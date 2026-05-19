#!/usr/bin/env python3
import sys

lines = open('/tmp/tradier_auto_trade.py').readlines()

# 1. Add import after the last import line
import_end = 0
for i, line in enumerate(lines):
    if line.strip() and not line.strip().startswith('import') and not line.strip().startswith('from'):
        import_end = i
        break
if import_end == 0:
    import_end = len(lines)
# Insert before the first non-import line
lines.insert(import_end, 'from trade_journal import log_trade\n')

# 2. Find the line with 'committed = service.record_commit(ready, broker_response)'
for i, line in enumerate(lines):
    if 'committed = service.record_commit(ready, broker_response)' in line:
        # Insert after this line
        indent = len(line) - len(line.lstrip())
        # Determine side
        # Find preceding payload dict
        for j in range(i-10, i):
            if "'side':" in lines[j]:
                side_raw = lines[j].split("'side':")[1].split(',')[0].strip().strip("'\"")
                if 'buy' in side_raw:
                    side = 'buy'
                else:
                    side = 'sell'
                break
        else:
            side = 'buy'
        # Build log line
        log_line = ' ' * indent + f'log_trade("tradier", candidate["symbol"], "{side}", args.qty, limit_price, notes=f"Auto trade {ready[\'intent_id\']}")\n'
        lines.insert(i+1, log_line)
        break

sys.stdout.write(''.join(lines))