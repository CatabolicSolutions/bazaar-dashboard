# Tradier Dashboard — Tomorrow Same-Network Access

## Goal

Make the current single-operator Tradier dashboard reachable from another machine/browser on the same private network.

This path is:
- same-network only
- single-operator only
- not public-internet safe
- no auth included

## Canonical launch

From the workspace root:

```bash
./scripts/run_tradier_dashboard_same_network.sh
```

Default serving mode:
- host bind: `0.0.0.0`
- port: `8765`

Optional override:

```bash
TRADIER_DASHBOARD_HOST=0.0.0.0 TRADIER_DASHBOARD_PORT=8765 ./scripts/run_tradier_dashboard_same_network.sh
```

## Browser entry URL

From Conor's other machine on the same network:

- `http://<lan-ip>:8765/app`

Local machine fallback:

- `http://127.0.0.1:8765/app`

## What should work

- page load: `GET /app`
- snapshot refresh path: `GET /snapshot.json`
- selected-item actions: `POST /api/actions`
- board/detail/actions/summary refresh coherence after action

## Tomorrow-use check

1. Launch with `./scripts/run_tradier_dashboard_same_network.sh`
2. Open `http://<lan-ip>:8765/app` from the other machine
3. Confirm leaders board loads
4. Select a Tradier leader
5. Run one local action:
   - `Queue Selected Ticket`, or
   - `Watch Selected Ticket`
6. Confirm the same page reflects:
   - queued/watch badge change
   - summary-strip update
   - recent action feedback
   - refresh still preserves selected-item coherence

## Safety posture

Use this only on a trusted private network.
Do not expose this port to the public internet.
