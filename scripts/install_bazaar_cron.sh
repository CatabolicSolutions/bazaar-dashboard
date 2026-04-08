#!/usr/bin/env bash
set -euo pipefail

WORKDIR="${1:-$HOME/.openclaw/workspace}"
CRON_LINE="*/15 6-14 * * 1-5 /bin/bash -lc 'cd $WORKDIR && ./scripts/bazaar_refresh_cycle.sh'"

EXISTING=$(crontab -l 2>/dev/null || true)
UPDATED=$(printf '%s
' "$EXISTING" | grep -v 'bazaar_refresh_cycle.sh' || true)
printf '%s
%s
' "$UPDATED" "$CRON_LINE" | crontab -

echo "Installed Bazaar refresh cron:"
crontab -l | grep 'bazaar_refresh_cycle.sh'
printf 'Workspace: %s\n' "$WORKDIR"
