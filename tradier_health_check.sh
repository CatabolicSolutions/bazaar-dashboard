#!/bin/bash
set -e

# Source environment variables
if [ -f "/var/www/bazaar/.bazaar.env" ]; then
    source "/var/www/bazaar/.bazaar.env"
fi

LOG_DIR="/home/alfred-deploy/logs"
HEALTH_LOG="$LOG_DIR/tradier_health.log"
BOARD_FILE="/home/alfred-deploy/out/tradier_leaders_board.txt"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

mkdir -p "$LOG_DIR"

{
    echo "=== TRADIER HEALTH CHECK $TIMESTAMP ==="

    # 1. Check API connectivity
    if [ -z "$TRADIER_API_KEY" ]; then
        echo "ERROR: TRADIER_API_KEY not set"
        exit 1
    fi

    API_RESPONSE=$(curl -s -H "Authorization: Bearer $TRADIER_API_KEY" \
        "https://api.tradier.com/v1/user/profile" \
        -w "%{http_code}" -o /tmp/tradier_api_check.json 2>/dev/null || echo "CURL_FAIL")

    if [ "$API_RESPONSE" = "CURL_FAIL" ]; then
        echo "ERROR: Tradier API curl failed (network)"
    elif [ "$API_RESPONSE" != "200" ]; then
        echo "ERROR: Tradier API returned HTTP $API_RESPONSE"
        cat /tmp/tradier_api_check.json 2>/dev/null | head -2
    else
        echo "OK: Tradier API connectivity (HTTP 200)"
    fi

    # 2. Check recent run
    if [ -f "$BOARD_FILE" ]; then
        LAST_MOD=$(stat -c %Y "$BOARD_FILE" 2>/dev/null || stat -f %m "$BOARD_FILE")
        NOW=$(date +%s)
        AGE=$((NOW - LAST_MOD))
        if [ $AGE -gt 7200 ]; then
            echo "WARNING: Leaders board is $((AGE/3600)) hours old (threshold 2h)"
        else
            echo "OK: Leaders board updated $((AGE/60)) minutes ago"
        fi
    else
        echo "WARNING: Leaders board file missing"
    fi

    # 3. Check cron log growth
    CRON_LOG="$LOG_DIR/tradier_cron.log"
    if [ -f "$CRON_LOG" ]; then
        LOG_SIZE=$(stat -c %s "$CRON_LOG" 2>/dev/null || stat -f %z "$CRON_LOG")
        if [ $LOG_SIZE -gt 1000000 ]; then
            echo "WARNING: Cron log large ($((LOG_SIZE/1024/1024)) MB), consider rotation"
        else
            echo "OK: Cron log size $((LOG_SIZE/1024)) KB"
        fi
    else
        echo "INFO: No cron log yet"
    fi

    # 4. Check disk space
    DF_OUT=$(df -h /home 2>/dev/null | tail -1)
    echo "DISK: $DF_OUT"

    echo "=== HEALTH CHECK END ==="
} 2>&1 | tee -a "$HEALTH_LOG"