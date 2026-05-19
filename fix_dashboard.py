#!/usr/bin/env python3
import sys
import os

file_path = '/var/www/bazaar/dashboard/scripts/serve_dashboard.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    stripped = line.lstrip()
    if stripped.startswith("data = response.json().get('data', []):") or "data = response.json().get('data', [])" in line:
        # preserve indentation
        indent = len(line) - len(line.lstrip())
        new_lines.append(' ' * indent + "json_response = response.json()\n")
        new_lines.append(' ' * indent + "data = json_response.get('series', {}).get('data', [])\n")
    else:
        new_lines.append(line)

if new_lines != lines:
    with open(file_path, 'w') as f:
        f.writelines(new_lines)
    print(f"Updated {file_path}")
else:
    print("Line not found, no changes made.")