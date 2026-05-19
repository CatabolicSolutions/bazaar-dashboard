# CREDENTIALS.md

Operational credential and auth notes that should not need rediscovery.

## Bazaar / VPS access
- VPS host: `137.184.144.196`
- Primary SSH key used from workspace host to access droplet:
  - `/home/catabolic_solutions/.ssh/alfred_deploy_key`
- Canonical Bazaar VPS deploy path:
  - `cd /var/www/bazaar && git pull origin master && sudo ./deploy/deploy.sh`

## Droplet GitHub auth state (important)
As of 2026-05-16:
- Droplet `/root/.ssh/` contains:
  - `id_ed25519`
  - `id_ed25519.pub`
  - `id_ed25519_marketplace_cockpit`
  - `id_ed25519_marketplace_cockpit.pub`
- `ssh -T git@github.com` from the droplet succeeds and identifies as:
  - `CatabolicSolutions/marketplace-cockpit`
- This means GitHub SSH auth exists on the box, but the currently working deploy key identity is **not authorized for every repo**.

## UniSwap_Rotator repo auth and main-lane truth
- Writable authoring repo on workspace host:
  - `/home/catabolic_solutions/.openclaw/workspace/UniSwap_Rotator`
- Live deploy repo on droplet:
  - `/var/www/uniswap_rotator`
- Canonical upstream repo:
  - `https://github.com/CatabolicSolutions/UniSwap_Rotator.git`

### Verified GitHub SSH identities on droplet
- `/root/.ssh/id_ed25519`
  - authenticates as: `CatabolicSolutions/bazaar-dashboard`
- `/root/.ssh/id_ed25519_marketplace_cockpit`
  - authenticates as: `CatabolicSolutions/marketplace-cockpit`
- `/root/.ssh/config` maps:
  - `github.com` -> `id_ed25519_marketplace_cockpit`
  - `github-rotator` -> `id_ed25519`

### Important behavior
- Droplet keys can **read/fetch** `UniSwap_Rotator`
- Droplet keys currently **cannot push** to `UniSwap_Rotator`
- Exact push error from droplet:
  - `Permission to CatabolicSolutions/UniSwap_Rotator.git denied to deploy key`
- Interpretation:
  - droplet is a **read/deploy lane** for this repo, not the authoritative write lane

### Correct operating model
- Make code commits/pushes for `UniSwap_Rotator` from the writable workspace repo:
  - `/home/catabolic_solutions/.openclaw/workspace/UniSwap_Rotator`
- Then deploy to droplet by fetching/resetting the droplet repo to upstream
- Do **not** rely on droplet-origin pushes for this repo unless repo key permissions are explicitly changed later

### Current verified rotator upstream/deploy state (2026-05-16)
- Upstream commit pushed from workspace repo:
  - `23569a4` — `Replace live bridge with BTC-only reversal execution path`
- Droplet was updated by fetch/reset to `origin/master` and service restart

## Agora / Bazaar / Rotator important runtime paths
- Agora app: `/var/www/agora`
- Bazaar app: `/var/www/bazaar`
- Live crypto runtime: `/var/www/uniswap_rotator`
- Agora public URL:
  - `https://137.184.144.196/agora/`
- Agora API local checks:
  - `http://127.0.0.1:8767/api/agora/position-monitor`
  - `http://127.0.0.1:8767/api/agora/rotator-hub`
  - `http://127.0.0.1:8767/api/agora/tradier-leaders`

## BTC review automation
- Installed review script on droplet:
  - `/usr/local/bin/btc_reversal_review.sh`
- Current cron schedule:
  - `0 0,12 * * * /usr/local/bin/btc_reversal_review.sh`
- Review artifacts:
  - `/var/www/uniswap_rotator/runtime_data/logs/btc_only_matrix_review.json`
  - `/var/www/uniswap_rotator/runtime_data/logs/btc_reversal_120h_review.json`

## SSL note
- Direct Python HTTPS verification against `https://137.184.144.196/agora/` hit certificate verification mismatch.
- `curl -k` succeeds.
- If external browser behavior looks inconsistent, certificate chain correctness should be reviewed separately from app/data correctness.

## Kalshi Bazaar API credentials
- Account/email: `conor_ross@catabolicsolutions.com`
- Label: `Kalshi Bazaar`
- Team/workspace: `Kalshi Team Turtle`
- API key id: `978f3e5c-3502-410d-b994-1fc2018858df`
- Key name/id: `484a3823-6b21-42a4-aab2-a92ced0b6c95`
- Private key file: `/home/catabolic_solutions/.openclaw/workspace/credentials/kalshi_bazaar_private_key.pem`
- Required env:
  - `KALSHI_API_KEY=978f3e5c-3502-410d-b994-1fc2018858df`
  - `KALSHI_KEY_NAME=484a3823-6b21-42a4-aab2-a92ced0b6c95`
  - `KALSHI_KEY_PATH=/home/catabolic_solutions/.openclaw/workspace/credentials/kalshi_bazaar_private_key.pem`

## Coinbase AGORAALGO API credentials
- Purpose: Coinbase Advanced active crypto sleeve, initially read-only verification and no trades without explicit Conor approval.
- API key name path: `/home/catabolic_solutions/.openclaw/workspace/credentials/coinbase_agoraalgo_api_key_name.txt`
- EC private key path: `/home/catabolic_solutions/.openclaw/workspace/credentials/coinbase_agoraalgo_private_key.pem`
- Files are mode `600` under workspace `credentials/`.
- Verification 2026-05-18: Advanced REST auth works; perpetual products visible; open orders query returns zero; INTX/perpetual portfolio endpoints returned `PERMISSION_DENIED`, so portfolio permission/mapping still needs adjustment before live sleeve verification.
