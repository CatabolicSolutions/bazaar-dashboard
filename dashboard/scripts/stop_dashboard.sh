#!/bin/bash
set -euo pipefail
ROOT="$HOME/.openclaw/workspace"
PIDFILE="$ROOT/dashboard/dashboard.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  kill "$(cat "$PIDFILE")" || true
  sleep 1
fi
pkill -f serve_dashboard.py >/dev/null 2>&1 || true
rm -f "$PIDFILE"
echo "Dashboard stopped."
