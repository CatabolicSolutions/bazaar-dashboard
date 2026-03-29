# Tradier Local-Network Access Path

## Intended Mode

This path is for controlled same-network access only.

Use when:
- the shell should be reachable from another desktop browser on the same network
- the shell should be reachable from a phone browser on the same network

Do not treat this as a public-internet or hardened exposure mode.

## Runtime Shape

Use explicit local-network runtime config:
- host: `0.0.0.0`
- port: chosen operator port (example: `8123`)

## Current Access Path

Once started in local-network mode, use:
- browser page: `http://<host-or-lan-ip>:<port>/app`
- shell payload: `http://<host-or-lan-ip>:<port>/shell`
- action path: `http://<host-or-lan-ip>:<port>/shell/action`

## Current Safety Posture

This is still only a local/private-network usage path.
No auth, public exposure controls, or deployment hardening are included yet.
