#!/usr/bin/env python3
import sys
import os

lines = sys.stdin.read().splitlines(keepends=True)

# Find the second do_GET method
do_get_start = -1
do_get_end = -1
count = 0
for i, line in enumerate(lines):
    if line.strip() == 'def do_GET(self):':
        count += 1
        if count == 2:
            do_get_start = i
            break
if do_get_start == -1:
    sys.exit(1)

# Find the return super().do_GET() line within this method
for i in range(do_get_start + 1, len(lines)):
    if lines[i].strip() == 'return super().do_GET()':
        do_get_end = i
        break
if do_get_end == -1:
    sys.exit(1)

# Insert new elif clauses before the return statement
insert_line = do_get_end
while insert_line > do_get_start and lines[insert_line-1].strip() == '':
    insert_line -= 1

new_elif = [
    "        elif self.path == '/api/tradier/status':\n",
    "            return self._handle_tradier_status()\n",
    "        elif self.path == '/api/bloc/status':\n",
    "            return self._handle_bloc_status()\n",
    "        elif self.path == '/api/health':\n",
    "            return self._handle_health()\n",
]
lines[insert_line:insert_line] = new_elif

# Find the line where class ends (look for 'def parse_args' after the class)
class_end = -1
for i, line in enumerate(lines):
    if line.strip().startswith('def parse_args'):
        class_end = i
        break
if class_end == -1:
    sys.exit(1)

# Insert handlers before class_end
handler_methods = '''
    def _handle_tradier_status(self):
        """Return Tradier system status"""
        # Placeholder: implement with real data later
        return self.json_response(200, {
            'open_positions': [],
            'today_pnl': 0.0,
            'health': 'ok'
        })
    
    def _handle_bloc_status(self):
        """Return Bloc system status"""
        # Placeholder: implement with real data later
        return self.json_response(200, {
            'open_positions': [],
            'usdc_balance': 0.0,
            'health': 'ok'
        })
    
    def _handle_health(self):
        """Health check endpoint for deployment verification"""
        return self.json_response(200, {'status': 'ok'})
'''
lines.insert(class_end, handler_methods)

sys.stdout.write(''.join(lines))