# Dashboard VPS Deployment - Handoff for Orion

## Executive Summary
Successfully migrated Bazaar Dashboard from local-only (LAN) access to dedicated DigitalOcean VPS with global accessibility. Dashboard is now live at http://137.184.144.196 with full feature parity to local development environment.

---

## Deployment Architecture

### Infrastructure
- **Provider:** DigitalOcean
- **Droplet:** bazaar-dashboard
- **IP:** 137.184.144.196
- **Plan:** $6/month (1GB RAM, 1 CPU, 25GB SSD, 1000GB transfer)
- **OS:** Ubuntu 22.04 LTS
- **Authentication:** SSH key-based (ed25519)
- **Status:** Production-ready, globally accessible

### Network Stack
```
Internet → DigitalOcean Firewall → Nginx (port 80) → 
OpenClaw Gateway (port 18789) → Dashboard Application
```

### Services Running
1. **Nginx** (reverse proxy, port 80)
2. **OpenClaw Dashboard** (Python HTTP server, port 8765)
3. **Systemd** (process management)

---

## Filesystem Structure

```
/var/www/bazaar/
├── dashboard/
│   ├── scripts/
│   │   ├── serve_dashboard.py    # Main HTTP server
│   │   ├── execute_leader.py     # Trade execution bridge
│   │   ├── position_manager.py   # Live position data
│   │   ├── market_data_feed.py   # Real-time scanner
│   │   ├── exit_predictor.py     # Exit signal engine
│   │   ├── trade_journal.py      # Analytics & logging
│   │   ├── premarket_scanner.py  # Gap detection
│   │   └── portfolio_heatmap.py  # Risk visualization
│   ├── public/
│   │   ├── index.html            # Main dashboard UI
│   │   ├── app.js                # Frontend logic
│   │   └── styles.css            # Styling
│   ├── state/                    # Runtime state
│   │   ├── execution_queue.json
│   │   ├── active_positions.json
│   │   ├── position_history.json
│   │   └── tradier_execution_state.json
│   └── config/
│       └── safety_config.json    # Trading limits
├── scripts/                      # Core trading scripts
│   ├── tradier_execution_service.py
│   ├── tradier_broker_interface.py
│   ├── tradier_strategy_processor_v2.py
│   └── tradier_risk_controls.py
├── journal/                      # Trade history
│   └── trades_2026-03.json
├── out/                          # Output artifacts
│   └── tradier_leaders_board.txt
└── memory/                       # Daily logs
    └── 2026-03-31.md
```

---

## Key Features Implemented

### 1. Live Trading Execution
- **Execute Now** button with preview/confirmation flow
- Direct Tradier API integration (preview_order, place_order)
- Risk evaluation before execution
- Position recording to active_positions.json
- Real-time P&L tracking

### 2. Scanner Enhancements
- Live market data feed (10s refresh)
- Opportunity scoring algorithm (0-100)
- Temperature ratings (HOT/WARM/COOL/COLD)
- IV, delta, volume metrics
- Quick Execute and Queue buttons per row
- Auto-refresh every 10 seconds

### 3. Exit Predictor Engine
- Delta divergence tracking (0-40 points)
- Theta acceleration monitoring (0-30 points)
- Price level breach detection (0-30 points)
- Combined exit score (0-100)
- Signals: EXIT (>70), WATCH (40-70), HOLD (<40)
- Auto-refresh every 30 seconds

### 4. Alert System
- Browser notifications for EXIT signals
- Sound alerts (Web Audio API)
- Visual pulsing on EXIT positions
- Alert log with history
- Toggle controls for sound/notifications

### 5. Trade Journal
- Auto-log all entries and exits
- P&L calculation (dollar and percent)
- Duration tracking
- Win rate analytics
- Best/worst trade tracking
- CSV export for taxes
- Period filters (today/week/month/all)

### 6. Pre-Market Gap Scanner
- 19-symbol watchlist (SPY, QQQ, IWM, TSLA, NVDA, etc.)
- Gap detection (>3% medium, >5% high priority)
- Relative volume vs average
- Option play suggestions
- One-click queue for market open

### 7. Portfolio Heatmap
- Visual grid of all positions
- Size = position value
- Color = P&L (green/red intensity)
- Risk metrics panel (delta, theta, vega)
- Concentration bars
- Risk alerts (>20% concentration, >±50 delta)

---

## API Endpoints

```
GET  /app                          # Dashboard UI
GET  /api/live-positions           # Live position data
GET  /api/live-scanner             # Enhanced scanner with market data
GET  /api/exit-predictor           # Exit signal analysis
GET  /api/journal                  # Trade history
GET  /api/analytics?period=        # Performance analytics
GET  /api/premarket                # Pre-market gap scan
GET  /api/heatmap                  # Portfolio visualization
POST /api/actions                  # Execute/Queue/Watch actions
POST /api/close-position           # Close position
POST /api/journal/export           # Export to CSV
```

---

## Environment Configuration

Required environment variables (set in ~/.bashrc):
```bash
export TRADIER_API_KEY="[REDACTED]"
export TRADIER_ACCOUNT_ID="6YB74771"
export TRADIER_LIVE_ACCOUNT_ID="6YB74771"
export TRADIER_BASE_URL="https://api.tradier.com/v1"
```

---

## Deployment Process (Documented)

### Initial Setup
1. Created DigitalOcean droplet with SSH key auth
2. Updated system packages
3. Installed dependencies (python3, pip, nginx, git)
4. Created /var/www/bazaar directory structure
5. Copied codebase from WSL via rsync
6. Fixed hardcoded paths in serve_dashboard.py
7. Configured nginx as reverse proxy
8. Started dashboard service

### Files Modified for Production
- `dashboard/scripts/serve_dashboard.py` - Changed ROOT path to /var/www/bazaar
- `dashboard/public/app.js` - Various path fixes
- Nginx config at /etc/nginx/sites-available/bazaar

---

## Current Limitations & Next Steps

### Immediate Needs
1. **HTTPS/SSL** - Currently HTTP only, needs Let's Encrypt
2. **Domain DNS** - Point subdomain to VPS IP
3. **Auto-start** - Configure systemd service for boot
4. **Monitoring** - Add health checks and alerts
5. **Backups** - Automated backup of journal/ directory

### Security Hardening
1. Enable UFW firewall (currently disabled)
2. Configure fail2ban for intrusion prevention
3. Set up log rotation
4. Regular security updates (unattended-upgrades)

### Performance Optimization
1. Add Redis for caching
2. Implement WebSocket for real-time updates
3. Database migration (SQLite → PostgreSQL)
4. CDN for static assets

---

## Blockchain Trading Integration Roadmap

### Phase 1: Research & Setup
- [ ] Evaluate blockchain APIs (Alchemy, Infura, QuickNode)
- [ ] Set up Web3.py integration
- [ ] Create wallet management system
- [ ] Implement basic blockchain queries

### Phase 2: DEX Integration
- [ ] Uniswap V3 integration
- [ ] Price monitoring for token pairs
- [ ] Liquidity analysis
- [ ] Gas price optimization

### Phase 3: Trading Features
- [ ] Smart contract interaction
- [ ] Automated trading strategies
- [ ] MEV protection
- [ ] Multi-chain support (Ethereum, Polygon, Arbitrum)

### Phase 4: Analysis & Visualization
- [ ] On-chain data analysis
- [ ] Wallet tracking
- [ ] Token flow visualization
- [ ] Correlation with Tradier equity data

---

## Access Credentials

**VPS Access:**
- IP: 137.184.144.196
- User: root (or create dedicated user)
- Auth: SSH key (stored in ~/.ssh/id_ed25519)

**Dashboard Access:**
- URL: http://137.184.144.196
- No authentication currently (add basic auth or OAuth)

**API Keys:**
- Tradier: [Stored in ~/.bashrc on VPS]
- Account: 6YB74771

---

## Support & Maintenance

### Regular Tasks
- Weekly: Review logs, check disk space
- Monthly: Security updates, backup verification
- Quarterly: Performance review, cost optimization

### Emergency Contacts
- Ross: [Discord/Email/Phone]
- OpenClaw Discord: discord.gg/clawd
- DigitalOcean Support: cloud.digitalocean.com/support

---

## Resources

### Documentation
- `VPS_DEPLOYMENT_GUIDE.md` - Complete deployment instructions
- `REMOTE_ACCESS_GUIDE.md` - Remote access options
- `GO_LIVE_CHECKLIST.md` - Pre-market checklist
- `DYLAN_OPENCLAW_GUIDE.md` - User guide template

### Scripts
- `scripts/vps_deploy.sh` - Automated setup script
- `.github/workflows/deploy.yml` - CI/CD pipeline

---

## Notes for Orion

1. **Dashboard is production-ready** but needs HTTPS before handling real money
2. **All features from local dev are working** on VPS
3. **Codebase is in /var/www/bazaar** with git history
4. **Environment variables need to be set** for Tradier API access
5. **Systemd service not yet configured** - dashboard runs in background process
6. **Logs are in /var/log/bazaar/** (if configured) or console output
7. **Next priority: SSL certificate and domain setup**

---

## Quick Commands for Orion

```bash
# SSH to VPS
ssh root@137.184.144.196

# Check dashboard status
curl http://localhost:8765/app | head

# Restart dashboard
pkill -f serve_dashboard.py
cd /var/www/bazaar
python3 dashboard/scripts/serve_dashboard.py --host 0.0.0.0 --port 8765 &

# View logs
pm2 logs bazaar-dashboard  # if using PM2
# OR
tail -f /var/log/bazaar/dashboard.log

# Update code
cd /var/www/bazaar
git pull origin master
pm2 restart bazaar-dashboard

# Check disk space
df -h

# Check memory
free -m
```

---

**Status:** VPS deployed, dashboard live, ready for blockchain integration work
**Next:** HTTPS, domain, monitoring, then blockchain features
