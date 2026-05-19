#!/usr/bin/env python3
import sys
import os

file_path = '/var/www/bazaar/dashboard/scripts/serve_dashboard.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

# Find the second do_GET method (the one with many elifs)
in_do_get = False
do_get_start = -1
do_get_end = -1
for i, line in enumerate(lines):
    if line.strip() == 'def do_GET(self):':
        if do_get_start == -1:
            do_get_start = i
        else:
            # second occurrence
            do_get_start = i
            in_do_get = True
    elif in_do_get and line.strip() == 'return super().do_GET()':
        do_get_end = i
        break

if do_get_start == -1 or do_get_end == -1:
    print("Could not locate do_GET method")
    sys.exit(1)

print(f"do_GET lines: {do_get_start}-{do_get_end}")

# Insert new elif clauses before the return statement
# We'll insert after the last elif block before return
# Find the line just before the return
insert_line = do_get_end  # line of return statement
# Move up to find the line before return (could be empty line)
while insert_line > do_get_start and lines[insert_line-1].strip() == '':
    insert_line -= 1

# Now insert before that line
new_lines = [
    "        elif self.path == '/api/tradier/status':\n",
    "            return self._handle_tradier_status()\n",
    "        elif self.path == '/api/bloc/status':\n",
    "            return self._handle_bloc_status()\n",
    "        elif self.path == '/api/health':\n",
    "            return self._handle_health()\n",
]

lines[insert_line:insert_line] = new_lines

# Now add handler methods at the end of the class before parse_args function
# Find the line where class ends (look for 'def parse_args' after the class)
class_end = -1
for i, line in enumerate(lines):
    if line.strip().startswith('def parse_args'):
        class_end = i
        break

if class_end == -1:
    print("Could not find end of class")
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

# Write back
with open(file_path, 'w') as f:
    f.writelines(lines)

print(f"Patched {file_path}")