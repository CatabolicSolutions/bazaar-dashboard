#!/bin/bash
DATE=$(date +%Y-%m-%d)
LOG="/home/alfred-deploy/logs/tradier_cron.log"
SUMMARY_LOG="/home/alfred-deploy/logs/tradier_summary.log"
DISCORD_CHANNEL="1483025184775733319"

{
    echo "=== Tradier Daily Summary $DATE ==="
    echo "Signals: $(grep -c "leader" "$LOG" 2>/dev/null || echo "0")"
    echo "Intents: $(grep -c "intent" "$LOG" 2>/dev/null || echo "0")"
    echo "Errors: $(grep -c -i "error\|failed" "$LOG" 2>/dev/null || echo "0")"
    echo "Last run: $(tail -1 "$LOG" 2>/dev/null | cut -c1-50 || echo "No runs yet")"
    
    # Check for recent failures in health log
    HEALTH_LOG="/home/alfred-deploy/logs/tradier_health.log"
    if [ -f "$HEALTH_LOG" ]; then
        RECENT_FAILURES=$(grep -c "ERROR\|WARNING:" "$HEALTH_LOG" 2>/dev/null || echo "0")
        echo "Recent health warnings: $RECENT_FAILURES"
    fi
    
    echo "=== Summary End ==="
    
    # Send summary to Discord (optional)
    SUMMARY="📊 Tradier Daily Summary $DATE
Signals: $(grep -c "leader" "$LOG" 2>/dev/null || echo "0")
Intents: $(grep -c "intent" "$LOG" 2>/dev/null || echo "0")
Errors: $(grep -c -i "error\|failed" "$LOG" 2>/dev/null || echo "0")
Last run: $(tail -1 "$LOG" 2>/dev/null | cut -c1-50 || echo "No runs yet")"
    
    openclaw message action send target "$DISCORD_CHANNEL" message "$SUMMARY" 2>/dev/null || \
        echo "WARNING: Failed to send Discord summary"
} 2>&1 | tee -a "$SUMMARY_LOG"