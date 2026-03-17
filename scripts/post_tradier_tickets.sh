#!/bin/bash
set -uo pipefail

DISCORD_CHANNEL_ID="1483025184775733319"
PYTHON_WRAPPER_SCRIPT="$HOME/.openclaw/workspace/scripts/run_python_script.sh"
PYTHON_PROCESSOR_SCRIPT="$HOME/.openclaw/workspace/scripts/tradier_strategy_processor_v2.py"
PYTHON_FORMATTER_SCRIPT="$HOME/.openclaw/workspace/scripts/tradier_ticket_formatter.py"

TMP_RAW=$(mktemp)
TMP_BOARD=$(mktemp)
OUTPUT_BOARD_PATH="$HOME/.openclaw/workspace/out/tradier_leaders_board.txt"
mkdir -p "$(dirname "$OUTPUT_BOARD_PATH")"
trap 'rm -f "$TMP_RAW" "$TMP_BOARD"' EXIT

printf 'Running Tradier processor...\n' >&2
"$PYTHON_WRAPPER_SCRIPT" "$PYTHON_PROCESSOR_SCRIPT" > "$TMP_RAW" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    printf 'TRADIER RUN FAILURE\n' 
    printf 'Processor exited with code %s\n\n' "$EXIT_CODE"
    cat "$TMP_RAW"
    printf '\nSummary: Tradier processor failed before leaders-board formatting. No board posted.\n'
    exit $EXIT_CODE
fi

printf 'Formatting leaders board...\n' >&2
python3 "$PYTHON_FORMATTER_SCRIPT" < "$TMP_RAW" > "$TMP_BOARD" 2>&1
FORMAT_EXIT=$?

if [ $FORMAT_EXIT -ne 0 ]; then
    printf 'TRADIER RUN FAILURE\n'
    printf 'Formatter exited with code %s\n\n' "$FORMAT_EXIT"
    cat "$TMP_BOARD"
    printf '\nRaw processor output follows:\n\n'
    cat "$TMP_RAW"
    printf '\nSummary: Tradier formatter failed after processor completion. No clean leaders board was produced.\n'
    exit $FORMAT_EXIT
fi

cp "$TMP_BOARD" "$OUTPUT_BOARD_PATH"
cat "$TMP_BOARD"
