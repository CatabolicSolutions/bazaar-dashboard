#!/bin/bash
# Bazaar Health Check
# Usage: ./health-check.sh

set -uo pipefail

URL="http://137.184.144.196:8765"
LOG_FILE="/var/log/bazaar-health.log"

echo "=== BAZAAR HEALTH CHECK ===" | tee -a "$LOG_FILE"
echo "Time: $(date)" | tee -a "$LOG_FILE"

# Check HTTP response
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL" 2>/dev/null || echo "000")
echo "HTTP Status: $HTTP_CODE" | tee -a "$LOG_FILE"

if [ "$HTTP_CODE" != "200" ]; then
    echo "✗ CRITICAL: Dashboard not responding (HTTP $HTTP_CODE)" | tee -a "$LOG_FILE"
    exit 1
fi

# Check title
TITLE=$(curl -s "$URL" | grep -o '<title>[^<]*</title>' | sed 's/<[^>]*>//g')
echo "Dashboard Title: $TITLE" | tee -a "$LOG_FILE"

if [[ "$TITLE" == *"BAZAAR"* ]] || [[ "$TITLE" == *"Bazaar"* ]]; then
    echo "✓ Title check passed" | tee -a "$LOG_FILE"
else
    echo "⚠ Title check warning: expected BAZAAR in title" | tee -a "$LOG_FILE"
fi

# Check snapshot endpoint
SNAPSHOT=$(curl -s "$URL/snapshot.json" 2>/dev/null | head -1)
if [[ "$SNAPSHOT" == *"updatedAt"* ]]; then
    echo "✓ Snapshot endpoint responding" | tee -a "$LOG_FILE"
else
    echo "⚠ Snapshot endpoint issue" | tee -a "$LOG_FILE"
fi

# Check process
if pgrep -f "serve_dashboard.py" > /dev/null; then
    echo "✓ Bazaar process running" | tee -a "$LOG_FILE"
else
    echo "✗ CRITICAL: Bazaar process not found" | tee -a "$LOG_FILE"
    exit 1
fi

echo "=== HEALTH CHECK PASSED ===" | tee -a "$LOG_FILE"
exit 0
