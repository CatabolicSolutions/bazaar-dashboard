#!/bin/bash
# VPS Resync Script for Bazaar Dashboard
# Run this on the VPS to sync latest changes

set -e

echo "=== BAZAAR VPS RESYNC ==="
echo "Timestamp: $(date)"
echo ""

# Navigate to repo
cd /var/www/bazaar || {
    echo "ERROR: /var/www/bazaar not found"
    exit 1
}

echo "[1/5] Checking git status..."
git status --short

echo ""
echo "[2/5] Stashing any local changes..."
git stash || true

echo ""
echo "[3/5] Pulling latest from master..."
git pull origin master

echo ""
echo "[4/5] Verifying dashboard files..."
if [ -f "dashboard/public/index.html" ] && [ -f "dashboard/public/styles.css" ] && [ -f "dashboard/public/app.js" ]; then
    echo "✓ All dashboard files present"
else
    echo "✗ Missing dashboard files!"
    exit 1
fi

echo ""
echo "[5/5] Restarting dashboard service..."
# Find and restart the Python server
pkill -f "serve_dashboard.py" || true
sleep 1

# Start in background
nohup python3 dashboard/scripts/serve_dashboard.py --host 0.0.0.0 --port 8765 > /var/log/bazaar.log 2>&1 &
sleep 2

# Check if running
if pgrep -f "serve_dashboard.py" > /dev/null; then
    echo "✓ Dashboard service restarted"
    echo "✓ Available at: http://137.184.144.196:8765"
else
    echo "✗ Failed to start dashboard service"
    exit 1
fi

echo ""
echo "=== RESYNC COMPLETE ==="
echo "Latest commits:"
git log --oneline -3
