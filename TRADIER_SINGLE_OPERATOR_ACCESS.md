# Tradier Single-Operator Access / Hardening Contract

## Current Operator Assumption

Current intended operator count: **one**.

Conor is the only intended operator for the current served shell.
This stage is not designed as a public or multi-user system.

## Current Allowed Serving Modes

### 1. Private local mode (preferred default)
- bind host: `127.0.0.1`
- bind port: `8000`
- intended for same-machine use only

### 2. Controlled same-network mode
- bind host: `0.0.0.0`
- bind port: explicit operator-selected port (example: `8123`)
- intended only for Conor's own controlled devices on the same private network

## Current Hardening Expectations

At this stage, the shell should be treated as:
- private by default
- local/same-network only
- not internet-safe
- not multi-user
- not role-based

Operational expectations:
- prefer `127.0.0.1` unless cross-device access is intentionally needed
- only use `0.0.0.0` for controlled same-network operator access
- do not expose current shell directly to the public internet
- do not assume any built-in auth/identity boundary exists yet

## Current Routes in Scope

- `GET /app`
- `GET /shell`
- `POST /shell/action`

These routes are part of the single-operator shell only.
They should not be treated as public application endpoints.
