#!/usr/bin/env python3
import sys
import os

file_path = '/var/www/bazaar/dashboard/public/app.js'
with open(file_path, 'r') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    new_lines.append(line)
    if 'success: function(data) {' in line:
        # find the next line (should be opening brace line already added)
        # Insert console.log after the brace line
        # Determine indentation of next line (assuming it's inside the function)
        # Look ahead for the next non-empty line to get indentation
        j = i + 1
        while j < len(lines) and lines[j].strip() == '':
            j += 1
        if j < len(lines):
            indent = len(lines[j]) - len(lines[j].lstrip())
        else:
            indent = 8  # default
        # Insert after the current line
        new_lines.append(' ' * indent + "console.log('API response:', data);\n")
    i += 1

if new_lines != lines:
    with open(file_path, 'w') as f:
        f.writelines(new_lines)
    print(f"Updated {file_path}")
else:
    print("Pattern not found, no changes made.")