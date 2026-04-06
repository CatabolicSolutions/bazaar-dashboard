#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORKDIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$WORKDIR/out/logs"
LOG_FILE="$LOG_DIR/bazaar_refresh_cycle.log"
STATUS_FILE="$WORKDIR/dashboard/state/refresh_status.json"
mkdir -p "$LOG_DIR" "$(dirname "$STATUS_FILE")"

exec >>"$LOG_FILE" 2>&1

write_status() {
  local ok="$1"
  local stage="$2"
  local message="$3"
  python3 - "$ok" "$stage" "$message" "$STATUS_FILE" "$WORKDIR/dashboard/public/snapshot.json" "$WORKDIR/out/tradier_leaders_board.txt" <<'PY'
import json, datetime, pathlib, sys
status = pathlib.Path(sys.argv[4])
snapshot = pathlib.Path(sys.argv[5])
board = pathlib.Path(sys.argv[6])
status.parent.mkdir(parents=True, exist_ok=True)
status.write_text(json.dumps({
  "ok": sys.argv[1].lower() == "true",
  "stage": sys.argv[2],
  "message": sys.argv[3],
  "snapshotMtime": datetime.datetime.utcfromtimestamp(snapshot.stat().st_mtime).isoformat() + "Z" if snapshot.exists() else None,
  "boardMtime": datetime.datetime.utcfromtimestamp(board.stat().st_mtime).isoformat() + "Z" if board.exists() else None,
  "updatedAt": datetime.datetime.utcnow().isoformat() + "Z"
}, indent=2))
PY
}

on_failure() {
  local exit_code=${1:-$?}
  write_status false failed "Refresh cycle failed at stage: ${CURRENT_STAGE:-unknown}"
  echo "=== Bazaar refresh cycle failed: $(date -Is) | stage=${CURRENT_STAGE:-unknown} | code=$exit_code ==="
  exit "$exit_code"
}

on_timeout_or_termination() {
  local exit_code=${1:-124}
  write_status false timeout "Refresh cycle terminated before completion at stage: ${CURRENT_STAGE:-unknown}"
  echo "=== Bazaar refresh cycle terminated: $(date -Is) | stage=${CURRENT_STAGE:-unknown} | code=$exit_code ==="
  exit "$exit_code"
}
trap 'on_failure $?' ERR
trap 'on_timeout_or_termination 124' TERM INT

echo "=== Bazaar refresh cycle start: $(date -Is) ==="
cd "$WORKDIR"
write_status false starting "Refresh cycle starting"

if [[ -f "$WORKDIR/.bazaar.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$WORKDIR/.bazaar.env"
  set +a
elif [[ -f "$HOME/.bashrc" ]]; then
  # shellcheck disable=SC1090
  source "$HOME/.bashrc"
fi

CURRENT_STAGE="env"
if [[ -z "${TRADIER_API_KEY:-}" ]]; then
  write_status false env "TRADIER_API_KEY missing"
  echo "TRADIER_API_KEY missing"
  exit 1
fi

CURRENT_STAGE="tradier_strategy_processor"
python3 scripts/tradier_strategy_processor_v2.py > /tmp/bazaar_tradier_raw.txt
CURRENT_STAGE="tradier_ticket_formatter"
python3 scripts/tradier_ticket_formatter.py < /tmp/bazaar_tradier_raw.txt > out/tradier_leaders_board.txt
CURRENT_STAGE="tradier_near_miss_report"
python3 scripts/tradier_near_miss_report.py >/tmp/bazaar_near_miss_path.txt || true
CURRENT_STAGE="build_snapshot"
python3 dashboard/scripts/build_snapshot.py >/tmp/bazaar_snapshot_path.txt
CURRENT_STAGE="attach_decision_outcomes"
python3 dashboard/scripts/attach_decision_outcomes.py >/tmp/bazaar_outcome_attachments.txt || true
CURRENT_STAGE="confidence_calibration"
python3 dashboard/scripts/confidence_calibration.py >/tmp/bazaar_confidence_calibration.txt || true
CURRENT_STAGE="setup_quality_expectancy"
python3 dashboard/scripts/setup_quality_expectancy.py >/tmp/bazaar_setup_quality.txt || true
CURRENT_STAGE="preference_action_bias"
python3 dashboard/scripts/preference_action_bias.py >/tmp/bazaar_preference_bias.txt || true

CURRENT_STAGE="complete"
write_status true complete "Refresh cycle completed"

if ! git diff --quiet -- dashboard/public/snapshot.json out/tradier_leaders_board.txt dashboard/state/refresh_status.json; then
  git add dashboard/public/snapshot.json out/tradier_leaders_board.txt dashboard/state/refresh_status.json
  git commit -m "Auto-refresh: $(date -u +%Y-%m-%dT%H:%M:%SZ)" || true
  git push origin master || true
else
  echo "No dashboard artifact changes to commit"
fi

echo "=== Bazaar refresh cycle complete: $(date -Is) ==="