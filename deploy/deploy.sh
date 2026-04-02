#!/bin/bash
# Bazaar Deploy Script
# Usage: ./deploy.sh [branch] [environment]
# Example: ./deploy.sh staging staging
# Example: ./deploy.sh master production

set -euo pipefail

BRANCH=${1:-master}
ENV=${2:-production}
REPO_DIR="/var/www/bazaar"
LOG_FILE="/var/log/bazaar-deploy.log"
BACKUP_DIR="/var/www/bazaar-backups"
HEALTH_URL="http://localhost:8765"

echo "=== BAZAAR DEPLOY ===" | tee -a "$LOG_FILE"
echo "Branch: $BRANCH | Environment: $ENV | Time: $(date)" | tee -a "$LOG_FILE"

# Create backup
echo "[1/6] Creating backup..." | tee -a "$LOG_FILE"
mkdir -p "$BACKUP_DIR"
BACKUP_NAME="bazaar-$(date +%Y%m%d-%H%M%S).tar.gz"
tar -czf "$BACKUP_DIR/$BACKUP_NAME" -C "$REPO_DIR" . 2>/dev/null || echo "Warning: Backup failed, continuing..." | tee -a "$LOG_FILE"

# Navigate to repo
cd "$REPO_DIR" || { echo "ERROR: Cannot access $REPO_DIR" | tee -a "$LOG_FILE"; exit 1; }

# Fetch and checkout branch
echo "[2/6] Fetching branch: $BRANCH..." | tee -a "$LOG_FILE"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

# Install/update dependencies
echo "[3/6] Installing dependencies..." | tee -a "$LOG_FILE"
pip3 install -q -r requirements.txt 2>/dev/null || echo "No requirements.txt or pip install skipped"

# Restart service
echo "[4/6] Restarting Bazaar service..." | tee -a "$LOG_FILE"
pkill -f "serve_dashboard.py" 2>/dev/null || true
sleep 2

# Start service
nohup python3 "$REPO_DIR/dashboard/scripts/serve_dashboard.py" --host 0.0.0.0 --port 8765 >> "$LOG_FILE" 2>&1 &
sleep 3

# Health check
echo "[5/6] Health check..." | tee -a "$LOG_FILE"
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")

if [ "$HEALTH_STATUS" = "200" ]; then
    echo "✓ Health check passed (HTTP 200)" | tee -a "$LOG_FILE"
else
    echo "✗ Health check failed (HTTP $HEALTH_STATUS)" | tee -a "$LOG_FILE"
    echo "Initiating rollback..." | tee -a "$LOG_FILE"
    
    # Rollback
    pkill -f "serve_dashboard.py" 2>/dev/null || true
    cd "$REPO_DIR" && git reset --hard HEAD@{1} 2>/dev/null || true
    nohup python3 "$REPO_DIR/dashboard/scripts/serve_dashboard.py" --host 0.0.0.0 --port 8765 >> "$LOG_FILE" 2>&1 &
    
    echo "Rollback complete. Check $LOG_FILE for details." | tee -a "$LOG_FILE"
    exit 1
fi

# Verify content
echo "[6/6] Content verification..." | tee -a "$LOG_FILE"
TITLE=$(curl -s "$HEALTH_URL" | grep -o '<title>[^<]*</title>' | sed 's/<[^>]*>//g')
echo "✓ Dashboard title: $TITLE" | tee -a "$LOG_FILE"

echo "=== DEPLOY SUCCESS ===" | tee -a "$LOG_FILE"
echo "Backup: $BACKUP_DIR/$BACKUP_NAME" | tee -a "$LOG_FILE"
echo "Live at: http://137.184.144.196:8765" | tee -a "$LOG_FILE"
