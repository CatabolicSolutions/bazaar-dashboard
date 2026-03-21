#!/bin/bash
set -euo pipefail

PYTHON_WRAPPER_SCRIPT="$HOME/.openclaw/workspace/scripts/run_python_script.sh"
PYTHON_REPORT_SCRIPT="$HOME/.openclaw/workspace/scripts/daily_macro_report.py"
OUTPUT_PATH="$HOME/.openclaw/workspace/out/daily_macro_report.md"
STATE_PATH="$HOME/.openclaw/workspace/out/daily_macro_report_state.json"
TMP_OUT=$(mktemp)
trap 'rm -f "$TMP_OUT"' EXIT

"$PYTHON_WRAPPER_SCRIPT" "$PYTHON_REPORT_SCRIPT" > "$TMP_OUT"
mkdir -p "$(dirname "$OUTPUT_PATH")"
cp "$TMP_OUT" "$OUTPUT_PATH"
python3 - <<PY
import json
from datetime import datetime
from pathlib import Path
state_path = Path(${STATE_PATH@Q})
state_path.parent.mkdir(parents=True, exist_ok=True)
state = {
    'generated_at': datetime.now().astimezone().isoformat(),
    'output_path': ${OUTPUT_PATH@Q},
    'status': 'generated'
}
state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
PY
cat "$TMP_OUT"
