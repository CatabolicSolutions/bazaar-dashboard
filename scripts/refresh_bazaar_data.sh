#!/bin/bash
# Bazaar Data Refresh Script
# Runs Tradier board generation, snapshot build, and autonomous entry trigger

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
    echo "[3/4] Building snapshot..."
    python3 dashboard/scripts/build_snapshot.py
fi

# Attempt autonomous Tradier entry
if [ -f "scripts/tradier_auto_trade.py" ]; then
    echo "[4/4] Running autonomous Tradier entry..."
    python3 scripts/tradier_auto_trade.py --mode cash_day_trade --live || true
fi

echo "=== REFRESH COMPLETE ==="
echo "Time: $(date)"
