#!/bin/bash
# Bazaar Data Refresh Script
# Runs Tradier board generation and snapshot build

set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$(cd -- "$SCRIPT_DIR/.." && pwd)"

echo "=== BAZAAR DATA REFRESH ==="
echo "Time: $(date)"

# Run Tradier strategy processor
echo "[1/2] Generating Tradier leaders board..."
python3 scripts/tradier_strategy_processor_v2.py

# Run ticket formatter
echo "[2/2] Formatting tickets..."
python3 scripts/tradier_ticket_formatter.py

# Build snapshot (if build script exists)
if [ -f "dashboard/scripts/build_snapshot.py" ]; then
    echo "[3/3] Building snapshot..."
    python3 dashboard/scripts/build_snapshot.py
fi

echo "=== REFRESH COMPLETE ==="
echo "Time: $(date)"
