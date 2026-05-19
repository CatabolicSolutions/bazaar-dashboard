# Auto‑Execution Toggle – Tradier Pipeline

## Current State
- **Auto‑execution**: `TRADIER_AUTO_EXECUTE=false` (human‑in‑the‑loop)
- **Pipeline**: Scans options, produces leaders board, posts to Discord channel `1483025184775733319`.
- **Execution service**: `tradier_auto_trade.py` can automatically trade top leaders when enabled.

## How to Enable Auto‑Execution

### 1. Set environment flag
Edit `/var/www/bazaar/.bazaar.env` (or wrapper script) and add:
```bash
export TRADIER_AUTO_EXECUTE=true
```

Alternatively, modify `/home/alfred‑deploy/bazaar_scripts/run_python.sh`:
```bash
export TRADIER_AUTO_EXECUTE=true
```

### 2. Verify risk controls
Check `/var/www/bazaar/scripts/tradier_risk_controls.py` for:
- Max position size (default: 5% of account)
- Daily loss limit (default: 2% of account)
- Maximum number of concurrent positions (default: 3)

### 3. Enable execution in cron
Update the cron job to run `tradier_auto_trade.sh` instead of `post_tradier_tickets_final.sh`:
```bash
*/15 12-20 * * 1-5 cd /var/www/bazaar && ./scripts/tradier_auto_trade.sh >> logs/tradier_auto.log 2>&1
```

### 4. Monitoring
- Auto‑execution logs: `/var/www/bazaar/logs/tradier_auto.log`
- Positions: `/var/www/bazaar/out/tradier_account_state.json`
- Execution audit: `/var/www/bazaar/out/tradier_execution_audit.jsonl`

## Risk Controls (Manual Override)

### Emergency Stop
1. Set `TRADIER_AUTO_EXECUTE=false` in `.bazaar.env`
2. Kill any running auto‑trade processes:
   ```bash
   pkill -f "tradier_auto_trade"
   ```
3. Cancel open orders via Tradier dashboard.

### Position Monitoring
- Daily P&L summary at 7 AM MT (cron: `0 14 * * *`)
- Health‑check alerts for API failures or stale scans.

## Verification Steps
1. Run a test scan with auto‑execution disabled:
   ```bash
   TRADIER_AUTO_EXECUTE=false python3 scripts/tradier_strategy_processor_v2.py
   ```
2. Review leaders board (`/var/www/bazaar/out/tradier_leaders_board.txt`).
3. Enable auto‑execution and run a dry‑run:
   ```bash
   TRADIER_AUTO_EXECUTE=true python3 scripts/tradier_auto_trade.py --dry-run
   ```
4. Monitor logs for “EXECUTING LIVE TRADE” vs “DRY‑RUN”.

## Notes
- Auto‑execution respects the same filters as the scanner (delta, DTE, spread).
- Intents are created for each trade; review intents before enabling live execution.
- Ensure sufficient buying power in Tradier account (margin requirements for options).

---

**Last updated**: 2026‑04‑13 (Alfred)