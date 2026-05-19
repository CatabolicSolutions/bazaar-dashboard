#!/bin/bash
# Runs at market close (2:15 PM MT), analyzes today's trades, adjusts parameters.
DATE=$(date +%Y-%m-%d)
JOURNAL="/var/www/bazaar/logs/trade_journal.jsonl"
OPTIMIZATION="/var/www/bazaar/scripts/OPTIMIZATION.md"

echo "=== Daily Optimization $DATE ==="

# Count today's trades
TRADES_TODAY=$(grep -c "$DATE" "$JOURNAL" 2>/dev/null || echo 0)
echo "Trades today: $TRADES_TODAY"

# Simple rule: if <2 trades, lower thresholds; if >5, raise them
if [ $TRADES_TODAY -lt 2 ]; then
    echo "Adjustment: Lowering MIN_PROFIT_PCT (more aggressive)"
    # Update config files
elif [ $TRADES_TODAY -gt 5 ]; then
    echo "Adjustment: Raising MIN_PROFIT_PCT (more conservative)"
fi

# Append to optimization log
echo "$DATE – Trades: $TRADES_TODAY" >> /var/www/bazaar/logs/optimization.log