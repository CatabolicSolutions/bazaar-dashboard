#!/bin/bash
set -e

# Source environment variables
if [ -f "/var/www/bazaar/.bazaar.env" ]; then
    source "/var/www/bazaar/.bazaar.env"
fi

LOG_DIR="/home/alfred-deploy/logs"
HEALTH_LOG="$LOG_DIR/tradier_health.log"
BOARD_FILE="/var/www/bazaar/out/tradier_leaders_board.txt"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
DISCORD_CHANNEL="1483025184775733319"

mkdir -p "$LOG_DIR"

FAILED=0
FAILURE_REASONS=()

{
    echo "=== TRADIER HEALTH CHECK $TIMESTAMP ==="

    # 1. Check API connectivity
    if [ -z "$TRADIER_API_KEY" ]; then
        FAILED=$((FAILED + 1))
        FAILURE_REASONS+=("TRADIER_API_KEY not set")
        echo "ERROR: TRADIER_API_KEY not set"
    else
        API_RESPONSE=$(curl -s -H "Authorization: Bearer $TRADIER_API_KEY" \
            "https://api.tradier.com/v1/user/profile" \
            -w "%{http_code}" -o /tmp/tradier_api_check.json 2>/dev/null || echo "CURL_FAIL")

        if [ "$API_RESPONSE" = "CURL_FAIL" ]; then
            FAILED=$((FAILED + 1))
            FAILURE_REASONS+=("Tradier API curl failed (network)")
            echo "ERROR: Tradier API curl failed (network)"
        elif [ "$API_RESPONSE" != "200" ]; then
            FAILED=$((FAILED + 1))
            FAILURE_REASONS+=("Tradier API returned HTTP $API_RESPONSE")
            echo "ERROR: Tradier API returned HTTP $API_RESPONSE"
            cat /tmp/tradier_api_check.json 2>/dev/null | head -2
        else
            echo "OK: Tradier API connectivity (HTTP 200)"
        fi
    fi

    # 2. Check recent run
    if [ -f "$BOARD_FILE" ]; then
        LAST_MOD=$(stat -c %Y "$BOARD_FILE" 2>/dev/null || stat -f %m "$BOARD_FILE")
        NOW=$(date +%s)
        AGE=$((NOW - LAST_MOD))
        if [ $AGE -gt 7200 ]; then
            FAILED=$((FAILED + 1))
            FAILURE_REASONS+=("Leaders board is $((AGE/3600)) hours old (threshold 2h)")
            echo "WARNING: Leaders board is $((AGE/3600)) hours old (threshold 2h)"
        else
            echo "OK: Leaders board updated $((AGE/60)) minutes ago"
        fi
    else
        FAILED=$((FAILED + 1))
        FAILURE_REASONS+=("Leaders board file missing")
        echo "WARNING: Leaders board file missing"
    fi

    # 3. Check cron log growth
    CRON_LOG="$LOG_DIR/tradier_cron.log"
    if [ -f "$CRON_LOG" ]; then
        LOG_SIZE=$(stat -c %s "$CRON_LOG" 2>/dev/null || stat -f %z "$CRON_LOG")
        if [ $LOG_SIZE -gt 10000000 ]; then
            # Warning only, not a failure
            echo "WARNING: Cron log large ($((LOG_SIZE/1024/1024)) MB), consider rotation"
        else
            echo "OK: Cron log size $((LOG_SIZE/1024)) KB"
        fi
    else
        echo "INFO: No cron log yet"
    fi

    # 4. Check disk space
    DF_OUT=$(df -h /home 2>/dev/null | tail -1)
    DISK_PCT=$(echo "$DF_OUT" | awk '{print $5}' | sed 's/%//')
    if [ "$DISK_PCT" -gt 90 ]; then
        FAILED=$((FAILED + 1))
        FAILURE_REASONS+=("Disk usage >90%")
        echo "ERROR: Disk usage $DISK_PCT%"
    else
        echo "DISK: $DF_OUT"
    fi

    echo "=== HEALTH CHECK END ==="
    
    # Send alert if any failures
    if [ $FAILED -gt 0 ]; then
        ALERT_MESSAGE="❌ Tradier health‑check failed ($FAILED issue(s)): ${FAILURE_REASONS[0]}"
        # Send via OpenClaw message tool (same as pipeline)
        openclaw message action send target "$DISCORD_CHANNEL" message "$ALERT_MESSAGE" 2>/dev/null || \
            echo "WARNING: Failed to send Discord alert"
    fi
    
} 2>&1 | tee -a "$HEALTH_LOG"