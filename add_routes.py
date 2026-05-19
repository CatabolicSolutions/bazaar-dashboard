#!/usr/bin/env python3
import sys
import os

file_path = '/var/www/bazaar/dashboard/scripts/serve_dashboard.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

# Find line where if __name__ == '__main__': starts
insert_idx = -1
for i, line in enumerate(lines):
    if line.strip().startswith("if __name__ =="):
        insert_idx = i
        break

if insert_idx == -1:
    # fallback: insert at end
    insert_idx = len(lines)

# Routes to add
new_routes = '''
@app.route('/api/tradier/status', methods=['GET'])
def tradier_status():
    # TODO: integrate with actual Tradier pipeline
    import json, datetime
    return json.dumps({
        'system': 'tradier',
        'timestamp': datetime.datetime.utcnow().isoformat(),
        'open_positions': [],
        'health': 'ok',
        'last_scan': '2026-04-13T19:00:00Z'
    })

@app.route('/api/bloc/status', methods=['GET'])
def bloc_status():
    # TODO: integrate with actual Bloc pipeline
    import json, datetime
    return json.dumps({
        'system': 'bloc',
        'timestamp': datetime.datetime.utcnow().isoformat(),
        'open_positions': [],
        'health': 'ok',
        'last_trade': '2026-04-13T18:30:00Z'
    })
'''

# Insert before the if __name__ block
lines.insert(insert_idx, new_routes + '\n')

with open(file_path, 'w') as f:
    f.writelines(lines)
print(f"Added API routes at line {insert_idx}")