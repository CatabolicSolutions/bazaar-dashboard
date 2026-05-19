# R11 TUNING RECORD — ETH Scalper Bot

## Current Bot State (2026-05-02 23:17 MT)

**Side:** USDC ✅ — bot is holding cash, no open position
**Wallet value:** ~$248.58 USDC
**Bot status:** running (restarted 05:14 UTC with R11 config)
**Price:** ETH ~$2,307

Bot starts in USDC and only swaps to WETH when a buy signal fires. Currently waiting for entry conditions. The state file (`bot_state.json`) shows stale data from April 27 — wallet is reset on restart.

---

## R11 Parameter Set (LIVE on VPS)

### Constants changed
| Parameter | Old | New | Why |
|-----------|-----|-----|-----|
| `STOP_LOSS` | 0.15 | **0.25** | R0 had 24 stops in 2 days (-$4.33). Wider stop lets exits breathe past micro-retracements. |
| `REENTRY_SCORE_THRESHOLD` | 0.50 | **0.45** | Was blocking fair_recovery entries. Lower lets quality reclaims through without hitting arm_wait. |
| `VOL_FLOOR` | 0.12 | **0.15** | Raises minimum trigger band, keeps bot out during dead-vol zones. |
| `VOL_CAP` | 0.20 | **0.25** | Lets trigger scale higher during high-vol regimes. |
| `ARM_WAIT_ALLOWED` | _(new)_ | **0** | Blocks discounted_entry_signal from firing on arm_wait entries. This was the silent killer: 20/25 live entries were arm_wait with no quality setup. |
| `buy_signal` gate | _(unchanged)_ | `+ (ARM_WAIT_ALLOWED or entry_class != "arm_wait")` | Only ideal_dip entries can fire discounted_entry_signal. |

### Bugfix applied
- **recovery_mode scoping fix**: `recovery_mode` was used in entry_class logic (line ~699) before its assignment (line ~704). Python's local-variable scoping caused `referenced before assignment` error every loop cycle. Fixed by initializing `recovery_mode = False` before the entry_class block.

---

## Tuning Results (against 2191-tick bloc trace, May 1-2)

### R11 vs R0 (default live bot)
| Metric | R0 (default) | **R11 🏆** |
|--------|-------------|-----------|
| Win rate | 38.5% | **60%** |
| Net PnL | -$0.60 | **+$4.52** |
| Trades | 51 | **9** |
| Avg win | $0.32 | **$1.98** |
| Avg loss | -$0.33 | **-$0.71** |
| Stale exits | heavy | **0 stale** ✅ |
| Stop losses | 24 (-$4.33) | **0 stops** ✅ |

### What killed R0
1. **arm_wait entries**: `discounted_entry_signal` fired on any `p <= entry_target` with `two_cycle_edge >= 5%` regardless of entry class. Since `weth_ok` was usually false, the code fell into `arm_wait` (reentry_score >= 0.42). 20/25 entries were these phantom buys.
2. **Zero stops in R11**: widened STOP_LOSS to 0.25% eliminated the tight-stop whipsaw. Every exit in R11 was either take_profit or rollover — no stale losses.
3. **fair_recovery blocked at 0.50**: R2 had raised threshold to 0.50, which blocked ALL fair_recovery entries. R11 drops to 0.45 which lets marginal-quality reclaims through.

### Key discovery
The ARM_WAIT_ALLOWED gate + adjusted VOL band was the highest-leverage change set. Without it, stop losses alone didn't fix the arm_wait entry flood.

---

## How R11 Maps to Frontend

The `/bloc/` terminal now shows:
- **Top stat pills**: STOP_LOSS, VOL_FLOOR/CAP, REENTRY_SCORE_THRESHOLD, ARM_WAIT_ALLOWED
- **Bot Config panel** (bottom right): All parsed constants key-value
- Data source: `/api/hq/status` → `live.bot_config` (parsed live from main.py)

The HQ Cockpit (`/var/www/bazaar/bazaar-cockpit/`) still serves the old Scalp tab — it does not display bot_config. The canonical frontend for Bloc ops is `/bloc/`.

---

## Replay Artifact Locations

### On this machine (OpenClaw workspace)
| File | Location |
|------|----------|
| Tune Test 2 script | `/tmp/tune_test_2.py` |
| Replay harness | `eth_scalper/scripts/replay_bloc_trace.py` |
| Backtest grid sweep | `scripts/backtest_reversal_strategy.py` |
| Reversal analysis | `scripts/analyze_reversals.py` |
| Strategy lab page | `dashboard/public/strategy_lab.html` |

### On VPS
| File | Location |
|------|----------|
| Live bot | `/var/www/bazaar/eth_scalper/bot/main.py` |
| Backend | `/var/www/bazaar/dashboard/scripts/serve_dashboard.py` |
| Bloc frontend | `/var/www/bazaar/dashboard/public/bloc/index.html` |
| Replay script | `/tmp/replay_bloc_trace.py` |
| Tune test 2 | `/tmp/tune_test_2.py` |
| Bloc trace (2191 ticks) | `/var/www/bazaar/eth_scalper/state/bloc_trace.jsonl` |

---

## Recovery Instructions

If bot crashes or loses state:

1. **SSH in**: `ssh alfred-deploy@137.184.144.196`
2. **Check status**: `sudo systemctl status eth-scalper`
3. **View logs**: `sudo journalctl -u eth-scalper -n 50`
4. **Restart**: `sudo systemctl restart eth-scalper`
5. **Verify R11 params**: `curl -s http://localhost:8765/api/hq/status | python3 -c "import sys,json; print(json.load(sys.stdin)['live']['bot_config'])"`
6. **Check side**: The bot always starts in USDC. It only swaps to WETH on a buy signal.

---

## Future Work (not yet done)
- Step 2 of replay harness: parameterized CLI inputs (config file or flags instead of editing script)
- Live-dashboard params endpoint: `/bloc/` parameter sliders don't actually write to bot config (just show saved state)
- Cockpit frontend: could add bot_config display to the Scalp/Analyze tab
- Frontend stat pills could include COOLDOWN_SEC and REENTRY_SCORE_ARM_THRESHOLD for completeness
