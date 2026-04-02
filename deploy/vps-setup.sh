#!/bin/bash
# VPS Setup Script for Bazaar Pull-Based Deployment
# Run this once on the VPS to prepare the environment

set -euo pipefail

REPO_DIR="/var/www/bazaar"
BACKUP_DIR="/var/www/bazaar-backups"
DEPLOY_DIR="$REPO_DIR/deploy"

echo "=== BAZAAR VPS SETUP ==="
echo "Preparing VPS for pull-based deployment"

# Ensure git is configured
echo "[1/5] Checking git configuration..."
if [ ! -d "$REPO_DIR/.git" ]; then
    echo "Initializing git repo..."
    cd "$REPO_DIR"
    git init
    git remote add origin git@github.com:CatabolicSolutions/bazaar-dashboard.git
fi

# Create required directories
echo "[2/5] Creating directories..."
mkdir -p "$BACKUP_DIR"
mkdir -p "$DEPLOY_DIR"
mkdir -p /var/log

# Ensure deploy scripts are executable
echo "[3/5] Setting permissions..."
chmod +x "$DEPLOY_DIR"/*.sh 2>/dev/null || true

# Test git access
echo "[4/5] Testing git access..."
cd "$REPO_DIR"
if git fetch origin master 2>/dev/null; then
    echo "✓ Git access confirmed"
else
    echo "⚠ Git fetch failed - SSH key may need setup"
    echo "  Run: ssh-keygen -t ed25519 -C 'bazaar-deploy'"
    echo "  Then add ~/.ssh/id_ed25519.pub to GitHub deploy keys"
fi

# Create cron job for health checks (optional)
echo "[5/5] Optional: Setting up health check cron..."
(crontab -l 2>/dev/null | grep -v "health-check.sh"; echo "*/5 * * * * /var/www/bazaar/deploy/health-check.sh >/dev/null 2>&1") | crontab - 2>/dev/null || true

echo ""
echo "=== SETUP COMPLETE ==="
echo "Next steps:"
echo "1. Ensure SSH key is added to GitHub (if not done above)"
echo "2. Test deploy: sudo $DEPLOY_DIR/deploy.sh"
echo "3. Verify: curl http://localhost:8765"
echo ""
echo "Documentation: $REPO_DIR/DEPLOYMENT.md"
