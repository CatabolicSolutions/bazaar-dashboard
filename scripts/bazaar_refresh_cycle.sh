#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$HOME/.openclaw/workspace"
LOG_DIR="$WORKDIR/out/logs"
LOG_FILE="$LOG_DIR/bazaar_refresh_cycle.log"
STATUS_FILE="$WORKDIR/dashboard/state/refresh_status.json"
mkdir -p "$LOG_DIR" "$(dirname "$STATUS_FILE")"

exec >>"$LOG_FILE" 2>&1

echo "=== Bazaar refresh cycle start: $(date -Is) ==="
cd "$WORKDIR"

if [[ -f "$WORKDIR/.bazaar.env" ]]; then
  # shellcheck disable=SC1090
  source "$WORKDIR/.bazaar.env"
elif [[ -f "$HOME/.bashrc" ]]; then
  # shellcheck disable=SC1090
  source "$HOME/.bashrc"
fi

if [[ -z "${TRADIER_API_KEY:-}" ]]; then
  python3 - <<'PY'
import json, datetime, pathlib
p = pathlib.Path("dashboard/state/refresh_status.json")
p.write_text(json.dumps({
  "ok": False,
  "stage": "env",
  "message": "TRADIER_API_KEY missing",
  "updatedAt": datetime.datetime.utcnow().isoformat() + "Z"
}, indent=2))
PY
  echo "TRADIER_API_KEY missing"
  exit 1
fi

python3 scripts/tradier_strategy_processor_v2.py > /tmp/bazaar_tradier_raw.txt
python3 scripts/tradier_ticket_formatter.py < /tmp/bazaar_tradier_raw.txt > out/tradier_leaders_board.txt
python3 scripts/tradier_near_miss_report.py >/tmp/bazaar_near_miss_path.txt || true
python3 dashboard/scripts/build_snapshot.py >/tmp/bazaar_snapshot_path.txt

python3 - <<'PY'
import json, datetime, pathlib
snapshot = pathlib.Path('dashboard/public/snapshot.json')
board = pathlib.Path('out/tradier_leaders_board.txt')
status = pathlib.Path('dashboard/state/refresh_status.json')
status.write_text(json.dumps({
  "ok": True,
  "stage": "complete",
  "message": "Refresh cycle completed",
  "snapshotMtime": datetime.datetime.utcfromtimestamp(snapshot.stat().st_mtime).isoformat() + "Z" if snapshot.exists() else None,
  "boardMtime": datetime.datetime.utcfromtimestamp(board.stat().st_mtime).isoformat() + "Z" if board.exists() else None,
  "updatedAt": datetime.datetime.utcnow().isoformat() + "Z"
}, indent=2))
PY

if ! git diff --quiet -- dashboard/public/snapshot.json out/tradier_leaders_board.txt; then
  git add dashboard/public/snapshot.json out/tradier_leaders_board.txt dashboard/state/refresh_status.json
  git commit -m "Auto-refresh: $(date -u +%Y-%m-%dT%H:%M:%SZ)" || true
  git push origin master || true
else
  echo "No dashboard artifact changes to commit"
fi

echo "=== Bazaar refresh cycle complete: $(date -Is) ==="