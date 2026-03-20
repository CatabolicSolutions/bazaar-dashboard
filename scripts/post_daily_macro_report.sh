#!/bin/bash
set -euo pipefail

PYTHON_WRAPPER_SCRIPT="$HOME/.openclaw/workspace/scripts/run_python_script.sh"
PYTHON_REPORT_SCRIPT="$HOME/.openclaw/workspace/scripts/daily_macro_report.py"
OUTPUT_PATH="$HOME/.openclaw/workspace/out/daily_macro_report.md"
TMP_OUT=$(mktemp)
trap 'rm -f "$TMP_OUT"' EXIT

"$PYTHON_WRAPPER_SCRIPT" "$PYTHON_REPORT_SCRIPT" > "$TMP_OUT"
mkdir -p "$(dirname "$OUTPUT_PATH")"
cp "$TMP_OUT" "$OUTPUT_PATH"
cat "$TMP_OUT"
