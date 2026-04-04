#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$HOME/.openclaw/workspace"
CRON_LINE='*/15 6-14 * * 1-5 /bin/bash -lc "cd $HOME/.openclaw/workspace && ./scripts/bazaar_refresh_cycle.sh"'

tmp=$(mktemp)
crontab -l 2>/dev/null | grep -v 'bazaar_refresh_cycle.sh' > "$tmp" || true
printf '%s
' "$CRON_LINE" >> "$tmp"
crontab "$tmp"
rm -f "$tmp"
echo "Installed Bazaar refresh cron:" 
crontab -l | grep 'bazaar_refresh_cycle.sh'