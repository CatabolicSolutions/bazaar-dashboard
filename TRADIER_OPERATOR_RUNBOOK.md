# Tradier Operator Run/Usage Contract

## Current Intended Usage Posture

At this stage, the browser/app shell is intended for:
- private local use by default
- optional controlled local-network use
- not public internet exposure

No auth, publication, or deployment hardening is included yet.

## Start Modes

### 1. Default private mode

Use the runtime server with default config:
- host: `127.0.0.1`
- port: `8000`

Intended effect:
- accessible from the same machine only
- safest default posture for current milestone stage

### 2. Explicit local-network mode

Use the runtime server with an explicit bind such as:
- host: `0.0.0.0`
- port: chosen operator port (example: `8123`)

Intended effect:
- accessible from another device on the same network
- only for controlled local-network use
- still not treated as an internet/public exposure mode

## Current Key Routes / Entry Points

### Browser page
- `GET /app`
- First operator-facing browser shell page

### Shell payload
- `GET /shell`
- Returns the current shell payload in callable form

### Action path
- `POST /shell/action`
- Invokes allowed actions through the current action model and returns updated shell context

## First Operator Flow

1. Start server in private mode unless local-network access is intentionally needed
2. Open browser page at `/app`
3. Review overview/worklist/detail/actions
4. Invoke allowed actions through the current action path
5. Observe refreshed state through the shell/page loop

## Safe/Private Guidance

Current safe/default guidance:
- prefer `127.0.0.1:8000`
- only bind `0.0.0.0` when intentionally using the shell on another machine/device in a controlled network
- do not treat current scaffold as internet-safe
