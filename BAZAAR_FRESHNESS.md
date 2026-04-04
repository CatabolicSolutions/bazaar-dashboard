# Bazaar Freshness Operations

## Durable runtime secret source
Primary secret source:
- `~/.openclaw/workspace/.bazaar.env`

Expected format:
```bash
export TRADIER_API_KEY="YOUR_REAL_TRADIER_API_KEY"
```

Fallback source:
- `~/.bashrc`

## Install hardened cron
```bash
cd ~/.openclaw/workspace
./scripts/install_bazaar_cron.sh
```

## Verify installed cron
```bash
crontab -l | grep bazaar_refresh_cycle.sh
```

Expected schedule:
```cron
*/15 6-14 * * 1-5 /bin/bash -lc "cd $HOME/.openclaw/workspace && ./scripts/bazaar_refresh_cycle.sh"
```

## Run wrapper manually
```bash
cd ~/.openclaw/workspace
./scripts/bazaar_refresh_cycle.sh
```

## Verify success
```bash
cat dashboard/state/refresh_status.json
ls -l dashboard/public/snapshot.json out/tradier_leaders_board.txt
```

## Check logs
```bash
tail -100 out/logs/bazaar_refresh_cycle.log
```
