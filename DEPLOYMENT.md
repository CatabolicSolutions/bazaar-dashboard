# BAZAAR Deployment Pipeline

## Canonical Repo
**Repository:** `git@github.com:CatabolicSolutions/bazaar-dashboard.git`
**Local Path:** `~/.openclaw/workspace/`
**VPS Path:** `/var/www/bazaar`

## Branch Model

| Branch | Purpose | Deploy Target |
|--------|---------|---------------|
| `master` | Stable, production-ready code | Production VPS |
| `staging` | Accepted slices awaiting validation | Staging VPS (if available) or production with caution |
| `feature/*` | Active development workstreams | Local only |

### Current Branches
- `master` - Last known good
- `staging` - Integration branch
- `deploy-pipeline` - Infrastructure work (this slice)

## Operator Workflow

### 1. Local Development (Agent/You)
```bash
# Work on feature branch
git checkout -b feature/my-feature
# ... make changes ...
git add .
git commit -m "Description"
git push origin feature/my-feature
```

### 2. Promote to Staging
```bash
# Merge feature to staging
git checkout staging
git merge feature/my-feature
git push origin staging
```

### 3. Deploy Staging
```bash
# On VPS:
/var/www/bazaar/deploy/deploy.sh staging staging
```

### 4. Promote to Master (Production)
```bash
# When staging validated:
git checkout master
git merge staging
git push origin master
```

### 5. Deploy Production
```bash
# On VPS:
/var/www/bazaar/deploy/deploy.sh master production
```

## Deploy Script Usage

```bash
# Deploy master to production (default)
sudo /var/www/bazaar/deploy/deploy.sh

# Deploy specific branch
sudo /var/www/bazaar/deploy/deploy.sh staging staging

# Deploy with explicit environment
sudo /var/www/bazaar/deploy/deploy.sh master production
```

## Rollback

```bash
# Rollback to most recent backup
sudo /var/www/bazaar/deploy/rollback.sh

# Rollback to specific backup
sudo /var/www/bazaar/deploy/rollback.sh bazaar-20260401-120000.tar.gz
```

## Health Check

```bash
# Run health verification
/var/www/bazaar/deploy/health-check.sh

# Or manual check:
curl -s http://137.184.144.196:8765 | head
```

## Emergency Procedures

### Service Down
```bash
# SSH to VPS
ssh root@137.184.144.196

# Check if running
ps aux | grep serve_dashboard

# Restart manually
cd /var/www/bazaar
pkill -f serve_dashboard.py
nohup python3 dashboard/scripts/serve_dashboard.py --host 0.0.0.0 --port 8765 > /var/log/bazaar.log 2>&1 &
```

### Bad Deploy
```bash
# Immediate rollback
sudo /var/www/bazaar/deploy/rollback.sh
```

## File Locations

| Component | Path |
|-----------|------|
| Dashboard frontend | `/var/www/bazaar/dashboard/public/` |
| Deploy scripts | `/var/www/bazaar/deploy/` |
| Logs | `/var/log/bazaar-deploy.log` |
| Backups | `/var/www/bazaar-backups/` |
| Service | `python3 dashboard/scripts/serve_dashboard.py` |

## Verification Checklist

After any deploy, verify:
- [ ] http://137.184.144.196:8765 loads (HTTP 200)
- [ ] Dashboard title contains "BAZAAR"
- [ ] Snapshot endpoint returns JSON
- [ ] Process is running (`pgrep serve_dashboard`)
- [ ] No critical errors in logs
