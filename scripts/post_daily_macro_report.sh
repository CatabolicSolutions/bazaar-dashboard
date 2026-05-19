#!/bin/bash
set -euo pipefail

PYTHON_REPORT_SCRIPT="$HOME/.openclaw/workspace/scripts/daily_macro_report.py"
OUTPUT_PATH="$HOME/.openclaw/workspace/out/daily_macro_report.md"
STATE_PATH="$HOME/.openclaw/workspace/out/daily_macro_report_state.json"

exec 3>&1
TMP_OUT=$(mktemp)
trap 'rm -f "$TMP_OUT"' EXIT

python3 "$PYTHON_REPORT_SCRIPT" > "$TMP_OUT"
mkdir -p "$(dirname "$OUTPUT_PATH")"
cp "$TMP_OUT" "$OUTPUT_PATH"
python3 -c "
import json
from datetime import datetime
from pathlib import Path
state_path = Path('${STATE_PATH}')
state_path.parent.mkdir(parents=True, exist_ok=True)
state = {
    'generated_at': datetime.now().astimezone().isoformat(),
    'output_path': '${OUTPUT_PATH}',
    'status': 'generated'
}
state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
"
cat "$TMP_OUT"
