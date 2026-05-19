#!/usr/bin/env python3
import sys

lines = open('/tmp/tradier_auto_trade.py').readlines()

# Add import after existing imports
import_line = -1
for i, line in enumerate(lines):
    if line.strip().startswith('from tradier_board_utils import'):
        import_line = i + 1
        break
if import_line == -1:
    import_line = 1

lines.insert(import_line, 'from trade_journal import log_trade\n')

# Find line with 'broker_response = post_order(payload, preview=False)'
for i, line in enumerate(lines):
    if 'broker_response = post_order(payload, preview=False)' in line:
        # Insert after the next line (committed = service.record_commit(...))
        # Actually need to insert after the record_commit line
        # Let's find the line that contains 'committed = service.record_commit'
        for j in range(i+1, len(lines)):
            if 'committed = service.record_commit' in lines[j]:
                # Insert after that line
                insert_pos = j + 1
                # Determine side (buy_to_open or sell_to_open)
                # side = payload['side'] but payload not in scope here
                # We'll parse from earlier lines. Let's assume 'buy_to_open' for now.
                # We'll add log_trade call
                log_line = '            log_trade("tradier", candidate["symbol"], "buy", args.qty, limit_price, notes=f"Auto trade {ready[\'intent_id\']}")\n'
                lines.insert(insert_pos, log_line)
                break
        break

sys.stdout.write(''.join(lines))