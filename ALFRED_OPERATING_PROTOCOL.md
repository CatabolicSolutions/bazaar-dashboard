# 🚨 ALFRED'S OPERATING PROTOCOL — BINDING, NON-NEGOTIABLE

## PREAMBLE
This document exists because I habitually swap architectures instead of fixing the one we shipped. This kills trust, wastes cycles, and produces fragmented results. It stops here.

---

## I. THERE IS ONE ARCHITECTURE

The live bot. `/var/www/bazaar/eth_scalper/bot/dual_main.py` + `dual_rotator.py` on the DigitalOcean droplet. Deployed via `eth-scalper.service`. That's it.

- The replay harness is a **diagnostic tool**, period. It validates the live bot's logic on historical data. It does not produce alternative architectures.
- When the bot underperforms: tune the live parameters against the replay, then deploy. Do not swap engines.
- When structural changes are needed: modify the live bot code, then re-run the replay to validate. Do not build a parallel version in the workspace.

**Sign of violation:** I say "let me build a new engine" instead of "let me fix the existing one."

---

## II. GIT IS THE SOURCE OF TRUTH

Every config, every script, every tuning result, every structural change lives in git.

- The droplet bazaar repo (`/var/www/bazaar/`) is the canonical deployment repo. Changes go through `git push` + manual deploy.
- The workspace repo (`/home/catabolic_solutions/.openclaw/workspace/`) holds replay scripts, tuning runs, and analysis. These are committed with descriptive messages — not auto-refresh noise.
- Tuning results that inform live changes are **committed to the bazaar repo** or referenced by commit hash. No orphaned result files.
- Anything important enough to talk about is important enough to commit.

**Sign of violation:** I run a sweep, get a result, and move on without committing config files or decisions.

---

## III. THE REPLAY IS A DIAGNOSTIC, NOT A PLAYGROUND

The replay script tests one thing: **"Does the live bot's logic produce positive ETH-equiv return on historical data?"**

- The replay must always mirror the live bot's decision tree. If they diverge, fix the live bot, not the replay.
- When tuning: modify `dual_rotator.py` parameters, then run the replay with those same parameters.
- When adding features: add them to `dual_rotator.py` first, then update the replay to test them.
- Never build a feature in the replay that doesn't exist in the live bot. That's not research — it's procrastination.

**Sign of violation:** The replay has logic (rotate_state tracking, arm_wait suppression, churn guards) that the live bot doesn't. This gap must be closed by porting TO the live bot, not by running away from it.

---

## IV. WHAT "BEST SCRIPT" MEANS

The best script is the one that:
1. **Runs** on the droplet as `eth-scalper.service`
2. **Is committed** to the bazaar git repo
3. **The dashboard serves** — `/api/hq/status` returns its position, config, performance
4. **The charts reflect** — real-time price, trades, holds, rollovers on the cockpit

A config that produces +4.31% in a replay but isn't deployed is meaningless. A config that's deployed but not tuned is wasted.

---

## V. THE TUNING LOOP (MANDATORY)

When the bot needs improvement, this is the ONLY allowed loop:

1. **Identify the specific structural deficiency** in `dual_rotator.py` (e.g., "no post-rotate dwell for arm_wait suppression")
2. **Modify `dual_rotator.py`** to address it
3. **Run the replay** with the modified code to confirm improvement
4. **Commit to bazaar git** with message describing the change
5. **Deploy to droplet** and restart `eth-scalper.service`
6. **Verify dashboard** shows the new behavior running clean

Step 2 is non-negotiable. Porting from replay to live is not allowed — implement in live, then test with replay.

---

## VI. WHEN I CATCH MYSELF SWAPPING

If I ever start building a "new engine" or "different approach" or "better architecture":

**STOP.**
1. Read Section I of this document.
2. Ask: "What is broken in the existing bot?"
3. Fix that one thing.
4. Commit, deploy, verify.

If the answer to #2 is "I don't know," then run diagnostics (replay + trace dump), find the specific broken decision, and fix it. Do not guess. Do not rebuild.

---

## SIGNATURES

This document is binding. Violating it means I've chosen speculation over delivery, and I deserve whatever Conor says.

Alfred — bound 2026-05-07 05:15 MDT

---

## APPENDIX: CURRENT STATE (snapshot)

- **Live service:** `eth-scalper.service` on droplet, running `dual_main.py` → `dual_rotator.py` (r11)
- **Problem:** r11 was never tuned against any replay. Live bot's decision logic is unvalidated.
- **Structural gap:** r11 lacks rotate_state tracking, arm_wait suppression during rotate windows, post-rotate hold dwell, and proper churn guard.
- **Action:** These features are being ported INTO dual_rotator.py this session. Not built in replay first. Built in live code, validated by replay, committed, deployed.
- **Replay harness:** `/var/www/bazaar/eth_scalper/scripts/replay_live_bloc_protocol.py` (workspace copy: `eth_scalper/scripts/replay_*.py`)
- **Canonical source of truth for parameters:** `dual_rotator.py` constants.
