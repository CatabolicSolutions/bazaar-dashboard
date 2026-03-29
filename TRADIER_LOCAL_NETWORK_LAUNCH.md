# Tradier Local-Network Launch / Verification

## Intended Launch Mode

Use the runtime server in explicit same-network mode:
- host: `0.0.0.0`
- port: `8123`

This is for controlled local-network/private access only.

## Expected Browser Entry

Open from another device on the same network using:
- `http://<lan-ip>:8123/app`

## Expected Callable Routes

- page route: `GET /app`
- shell route: `GET /shell`
- action route: `POST /shell/action`

## Verification Expectations

When launched in same-network mode:
1. runtime config should report host `0.0.0.0`
2. browser page route should return the browser shell page payload
3. action route should remain callable under the same serving mode
4. posture remains local/private only; not internet-safe
