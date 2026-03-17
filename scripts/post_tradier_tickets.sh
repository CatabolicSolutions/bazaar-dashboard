#!/bin/bash

DISCORD_CHANNEL_ID="1483025184775733319"
PYTHON_WRAPPER_SCRIPT="$HOME/.openclaw/workspace/scripts/run_python_script.sh"
PYTHON_PROCESSOR_SCRIPT="$HOME/.openclaw/workspace/scripts/tradier_strategy_processor_v2.py"
PYTHON_FORMATTER_SCRIPT="$HOME/.openclaw/workspace/scripts/tradier_ticket_formatter.py"

TMP_RAW=$(mktemp)
TMP_BOARD=$(mktemp)
OUTPUT_BOARD_PATH="$HOME/.openclaw/workspace/out/tradier_leaders_board.txt"
mkdir -p "$(dirname "$OUTPUT_BOARD_PATH")"
trap 'rm -f "$TMP_RAW" "$TMP_BOARD"' EXIT

echo "Running Tradier processor..."
$PYTHON_WRAPPER_SCRIPT $PYTHON_PROCESSOR_SCRIPT > "$TMP_RAW"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "Error: Python script exited with code $EXIT_CODE. Output:"
    cat "$TMP_RAW"
    exit $EXIT_CODE
fi

echo "Formatting leaders board..."
python3 "$PYTHON_FORMATTER_SCRIPT" < "$TMP_RAW" > "$TMP_BOARD"
FORMAT_EXIT=$?

if [ $FORMAT_EXIT -ne 0 ]; then
    echo "Error: Formatter failed with code $FORMAT_EXIT. Raw output:"
    cat "$TMP_RAW"
    exit $FORMAT_EXIT
fi

cp "$TMP_BOARD" "$OUTPUT_BOARD_PATH"
cat "$TMP_BOARD"
echo
echo "Tradier board generation complete. Target Discord channel: $DISCORD_CHANNEL_ID"
echo "Saved board artifact: $OUTPUT_BOARD_PATH"
