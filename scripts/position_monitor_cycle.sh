#!/bin/bash
set -euo pipefail

cd "$HOME/.openclaw/workspace"

python3 scripts/position_monitor.py >/tmp/position_monitor_report.log 2>/tmp/position_monitor_report.err
python3 scripts/position_monitor_alerts.py >/tmp/position_monitor_alerts.log 2>/tmp/position_monitor_alerts.err
python3 scripts/position_monitor_telegram_push.py >/tmp/position_monitor_push.log 2>/tmp/position_monitor_push.err
python3 scripts/position_monitor_summary_push.py >/tmp/position_monitor_summary.log 2>/tmp/position_monitor_summary.err || true
