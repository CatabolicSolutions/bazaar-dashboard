#!/bin/bash
# Bazaar Rollback Script
# Usage: ./rollback.sh [backup-file]
# Example: ./rollback.sh bazaar-20260401-120000.tar.gz

set -euo pipefail

BACKUP_FILE=${1:-""}
REPO_DIR="/var/www/bazaar"
BACKUP_DIR="/var/www/bazaar-backups"
LOG_FILE="/var/log/bazaar-deploy.log"

echo "=== BAZAAR ROLLBACK ===" | tee -a "$LOG_FILE"
echo "Time: $(date)" | tee -a "$LOG_FILE"

# Find backup if not specified
if [ -z "$BACKUP_FILE" ]; then
    echo "No backup specified, finding most recent..." | tee -a "$LOG_FILE"
    BACKUP_FILE=$(ls -t "$BACKUP_DIR"/bazaar-*.tar.gz 2>/dev/null | head -1)
    if [ -z "$BACKUP_FILE" ]; then
        echo "ERROR: No backup found in $BACKUP_DIR" | tee -a "$LOG_FILE"
        exit 1
    fi
    BACKUP_FILE=$(basename "$BACKUP_FILE")
fi

BACKUP_PATH="$BACKUP_DIR/$BACKUP_FILE"

if [ ! -f "$BACKUP_PATH" ]; then
    echo "ERROR: Backup not found: $BACKUP_PATH" | tee -a "$LOG_FILE"
    exit 1
fi

echo "Rolling back to: $BACKUP_FILE" | tee -a "$LOG_FILE"

# Stop service
echo "[1/3] Stopping Bazaar service..." | tee -a "$LOG_FILE"
pkill -f "serve_dashboard.py" 2>/dev/null || true
sleep 2

# Restore backup
echo "[2/3] Restoring backup..." | tee -a "$LOG_FILE"
rm -rf "$REPO_DIR"/*
tar -xzf "$BACKUP_PATH" -C "$REPO_DIR"

# Restart service
echo "[3/3] Restarting service..." | tee -a "$LOG_FILE"
nohup python3 "$REPO_DIR/dashboard/scripts/serve_dashboard.py" --host 0.0.0.0 --port 8765 >> "$LOG_FILE" 2>&1 &
sleep 3

# Verify
if curl -s http://localhost:8765 >/dev/null 2>&1; then
    echo "✓ Rollback successful, service running" | tee -a "$LOG_FILE"
else
    echo "✗ Rollback verification failed" | tee -a "$LOG_FILE"
    exit 1
fi

echo "=== ROLLBACK COMPLETE ===" | tee -a "$LOG_FILE"
