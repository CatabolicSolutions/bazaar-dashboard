#!/usr/bin/env python3
import sys
import os

file_path = '/var/www/bazaar/dashboard/public/app.js'
with open(file_path, 'r') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    if 'success:' in line and 'function(data)' in line:
        # get indentation of this line
        indent = len(line) - len(line.lstrip())
        # Insert console.log after this line
        new_lines.append(' ' * indent + '    console.log("API response:", data);\n')

if new_lines != lines:
    with open(file_path, 'w') as f:
        f.writelines(new_lines)
    print(f"Updated {file_path}")
else:
    print("Pattern not found, no changes made.")