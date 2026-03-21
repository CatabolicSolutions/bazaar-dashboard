#!/bin/bash
set -euo pipefail
cd "$HOME/.openclaw/workspace"
python3 -m unittest tests/test_tradier_stack.py -v
