#!/bin/bash

# Path to your Python script and wrapper
PYTHON_WRAPPER_SCRIPT="$HOME/.openclaw/workspace/scripts/run_python_script.sh"
PYTHON_PROCESSOR_SCRIPT="$HOME/.openclaw/workspace/scripts/kalshi_strategy_processor.py"

# --- Execute Python script and capture output ---
echo "Running Kalshi processor script..."
OUTPUT=$($PYTHON_WRAPPER_SCRIPT $PYTHON_PROCESSOR_SCRIPT)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "Error: Python script exited with code $EXIT_CODE. Output:"
    echo "$OUTPUT"
    exit $EXIT_CODE
fi

echo "Python script finished. Parsing output..."
echo "$OUTPUT" # Simply output the raw Python script output
echo "Kalshi ticket processing for Alfred complete." # Status message

