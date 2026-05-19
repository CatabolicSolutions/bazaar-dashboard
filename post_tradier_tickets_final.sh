#!/bin/bash
set -uo pipefail

DISCORD_CHANNEL_ID="1483025184775733319"
PYTHON_WRAPPER_SCRIPT="/home/alfred-deploy/bazaar_scripts/run_python.sh"
PYTHON_PROCESSOR_SCRIPT="/var/www/bazaar/scripts/tradier_strategy_processor_v2.py"
PYTHON_FORMATTER_SCRIPT="/var/www/bazaar/scripts/tradier_ticket_formatter.py"
PYTHON_ARCHIVE_SCRIPT="/var/www/bazaar/scripts/tradier_archive_run.py"

TMP_RAW=$(mktemp)
TMP_BOARD=$(mktemp)
OUTPUT_BOARD_PATH="/var/www/bazaar/out/tradier_leaders_board.txt"
LOG_DIR="/home/alfred-deploy/logs"
mkdir -p "$(dirname "$OUTPUT_BOARD_PATH")"
mkdir -p "$LOG_DIR"
trap 'rm -f "$TMP_RAW" "$TMP_BOARD"' EXIT

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/tradier_$TIMESTAMP.log"

{
printf '=== TRADIER RUN %s ===\n' "$TIMESTAMP"
printf 'Running Tradier processor...\n'
"$PYTHON_WRAPPER_SCRIPT" "$PYTHON_PROCESSOR_SCRIPT" > "$TMP_RAW" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    printf 'TRADIER RUN FAILURE\n'
    printf 'Processor exited with code %s\n\n' "$EXIT_CODE"
    cat "$TMP_RAW"
    printf '\nSummary: Tradier processor failed before leaders-board formatting. No board posted.\n'
    exit $EXIT_CODE
fi

printf 'Formatting leaders board...\n'
"$PYTHON_WRAPPER_SCRIPT" "$PYTHON_FORMATTER_SCRIPT" < "$TMP_RAW" > "$TMP_BOARD" 2>&1
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
"$PYTHON_WRAPPER_SCRIPT" "$PYTHON_ARCHIVE_SCRIPT" --raw "$TMP_RAW" --board "$TMP_BOARD" >/dev/null 2>&1 || true
printf 'Success. Leaders board written to %s\n' "$OUTPUT_BOARD_PATH"
cat "$TMP_BOARD"
} 2>&1 | tee "$LOG_FILE"