# MEMORY.md

## Bazaar of Fortunes - Durable Operating Memory

### Identity and role
- Alfred is Conor Ross Leigh's execution-focused trading and market-ops copilot.
- Tone and operating style: calm, concise, disciplined, objective.
- Mission emphasis: precision, structure, consistency, risk-aware ticketing, operational clarity, and logs for review.

### Bazaar core workflow
Bazaar of Fortunes is being built in Discord and currently has separate rooms for:
- Tradier leaders-board / ticket output
- trading journal / logs
- coordination
- live position management
- Kalshi prediction-market review

### Tradier durable state
The Tradier workflow has already been materially rebuilt from noisy raw output into a leaders-board pipeline.

Current Tradier pipeline:
- `scripts/tradier_strategy_processor_v2.py`
- `scripts/tradier_ticket_formatter.py`
- `scripts/post_tradier_tickets.sh`
- board artifact: `out/tradier_leaders_board.txt`

Tradier durable truths:
- DTE labels are now truthful; fallback expiries are explicitly marked
- output is filtered, ranked, capped, and represented as leaders rather than chain spam
- normal output standard is summary-only leaders-board posting, not raw dumps
- direct cross-provider Discord sending from Telegram context is blocked; Discord-context delivery should own final posting
- VPS deployment: pipeline runs on Bazaar droplet with cron scheduling, health checks, and logs in /home/alfred‑deploy/

### Kalshi durable state
Kalshi auth/runtime is functioning.

Current Kalshi pipeline:
- `scripts/kalshi_strategy_processor.py`
- `scripts/post_kalshi_tickets.sh`
- `scripts/run_python_script.sh`

Kalshi durable truths:
- `/coinflip` is the intended plain-text trigger for Kalshi review / leaders / recommendation flow
- current Kalshi engine supports `No Trade` and rejection audits
- major remaining blockers are discovery quality and contract interpretation, not auth/runtime
- sampled live open feed has often been dominated by combinatoric cross-category noise and many contracts only expose shallow metadata in the current pull
- approved next direction is a probability-first refactor: implied probability -> fair probability estimate -> edge score -> execution validation

### Kalshi preference model
Highest-priority Kalshi markets:
- macro / economic data
- Fed / rates
- CPI / inflation / GDP / unemployment / claims
- index-close / range contracts
- corporate-event / earnings contracts

Preferred Kalshi setup archetypes:
- mispricing / arbitrage vs external anchor
- high-probability yield
- event-driven asymmetry

Category tolerance:
- sports should not be categorically rejected if a contract is structurally clean and survives edge/clarity/pricing filters
- politics are no by default except rare economically legible binaries
- crypto-event markets require high scrutiny and default to no unless edge is unusually clear

### Discord continuity mitigation
There is a known continuity gap across surfaces/sessions.
To mitigate this:
- maintain canonical system truth in `BAZAAR_OPERATING_STATE.md`
- use stable wording for trigger semantics, channel IDs, and current pipelines
- do not rely only on daily notes or ad hoc chat context for active system architecture

### Trade management durable lesson
A real IWM 248 call scalp was managed and closed green at roughly +5.1% in 21 minutes.
Durable lesson: take disciplined green instead of overstaying for uncertain extension.

### Default continuity recovery order
When recovering context for Bazaar work, consult in this order:
1. `BAZAAR_OPERATING_STATE.md`
2. `USER.md`
3. recent daily notes in `memory/`
4. relevant scripts / committed pipeline files

### Operational mandates - token efficiency protocol
- Default reply standard is minimal-noise, high-signal execution reporting.
- For slice completion reports, return `DONE` or `BLOCKED` only.
- Lead every `DONE` report with `commit:` as the first content line.
- Use one-line summaries only; avoid paragraphs, speculative next steps, and redundant repetition.
- If files are unchanged from a recent slice, say `same as prior commit` instead of relisting.
- If blocked, state the exact blocker and smallest needed input in one sentence each.
- Treat token efficiency and anti-bloat discipline as standing operational mandates, not temporary preferences.

- Bazaar VPS deploy command is cd /var/www/bazaar && git pull origin master && sudo ./deploy/deploy.sh.

### Recent Operational Events (2026-04-12)
- **Tradier leaders-board pipeline** ran successfully, delivering filtered premium/directional leaders to Discord channel `1483025184775733319`. All posted leaders were fallback-expiry candidates; confidence moderate. No clean directional edge surfaced.
- **Bazaar droplet eth-scalper service** deployment and verification completed. SSH key `alfred_deploy_key` works for login; sudoers rule added for passwordless service management. Service restarted and verified running with durable lifecycle code (resumable positions). Host proof collected: commit `65cf4dfc2a6355b20fedb3aeed75f49441b4fa5e`. Live wallet underfunded for entry.
- **New model configuration** inquiry: user asked about running on a newly configured model (awaiting confirmation).

### Recent Operational Events (2026-04-13)
- **Tradier pipeline VPS deployment** – Fixed broken paths, created wrapper scripts, installed cron scheduling (market‑hours every 15 min), added health‑check and log rotation. Pipeline now runs autonomously on the Bazaar droplet, writing leaders board to `/var/www/bazaar/out/tradier_leaders_board.txt`. API connectivity verified.
- **Auto‑execution decision pending** – Human‑in‑the‑loop remains default; toggle for live trades can be added.
- **Permission fix applied** – User provided sudo; ownership changed for `/var/www/bazaar/out/` and `/var/www/bazaar/logs/`. Updated pipeline script writes directly to central location (`/var/www/bazaar/out/tradier_leaders_board.txt`). Cron job updated to final script. TRADIER_AUTO_EXECUTE=false flag added via wrapper.
- **Pipeline fully operational** – Cron schedule: `*/15 12-20 * * 1-5` (6 AM‑2 PM MT), hourly health checks, weekly log cleanup, daily summary at 7 AM MT.
- **Discord alerting** – Health‑check failures trigger Discord alerts (channel `1483025184775733319`), pending OpenClaw installation on VPS.
- **Auto‑execution documentation** – Created `AUTO_EXECUTION_README.md` with toggle instructions and risk controls.
- **Remaining blockers** – OpenClaw not installed (Discord posting fails); `tradier_execution_state.json` owned by root (blocks auto‑trade dry‑run).
