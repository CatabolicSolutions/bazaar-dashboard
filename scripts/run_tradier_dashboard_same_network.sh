#!/usr/bin/env bash
set -euo pipefail

cd "$HOME/.openclaw/workspace"

HOST="${TRADIER_DASHBOARD_HOST:-0.0.0.0}"
PORT="${TRADIER_DASHBOARD_PORT:-8765}"
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

cat <<EOF
Tradier dashboard same-network launch
- Host bind: ${HOST}
- Port: ${PORT}
- Local URL: http://127.0.0.1:${PORT}/app
- LAN URL:   http://${LAN_IP:-<lan-ip>}:${PORT}/app

Private/same-network only.
Not public-internet safe.
EOF

exec python3 dashboard/scripts/serve_dashboard.py --host "$HOST" --port "$PORT"
