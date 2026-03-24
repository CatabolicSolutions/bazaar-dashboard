#!/bin/bash
set -euo pipefail
ROOT="$HOME/.openclaw/workspace"
PIDFILE="$ROOT/dashboard/dashboard.pid"
LOGFILE="$ROOT/dashboard/dashboard.log"
PORT="8765"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Dashboard already running (PID $(cat "$PIDFILE"))"
  exit 0
fi

python3 "$ROOT/dashboard/scripts/serve_dashboard.py" >> "$LOGFILE" 2>&1 &
PID=$!
echo "$PID" > "$PIDFILE"
sleep 2
if curl -sSf "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
  echo "Dashboard started on http://127.0.0.1:$PORT (PID $PID)"
else
  echo "Dashboard may not have started cleanly. Check $LOGFILE"
  exit 1
fi
