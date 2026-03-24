#!/bin/bash
set -euo pipefail
ROOT="$HOME/.openclaw/workspace"
PIDFILE="$ROOT/dashboard/dashboard.pid"
URL="http://127.0.0.1:8765/"
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "PID: $(cat "$PIDFILE")"
else
  echo "PID: not running"
fi
if curl -sSf "$URL" >/dev/null 2>&1; then
  echo "HTTP: OK ($URL)"
else
  echo "HTTP: FAIL ($URL)"
fi
