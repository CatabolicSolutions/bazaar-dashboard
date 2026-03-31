# Remote Access Options for Bazaar Dashboard

## Problem
Dashboard currently only accessible on local network (192.168.220.149:8765)
Need remote access for mobile/away-from-home trading

## Recommended Solutions

### Option 1: Cloud VPS Deployment (BEST)
Deploy dashboard to a cloud server accessible from anywhere

**Providers:**
- DigitalOcean Droplet ($5/month)
- AWS EC2 t2.micro (free tier eligible)
- Linode Nanode ($5/month)
- Hetzner Cloud (~$3/month)

**Steps:**
1. Create Ubuntu 22.04 VPS
2. Clone repository: `git clone https://github.com/yourusername/bazaar-dashboard.git`
3. Install dependencies (Node.js, Python)
4. Set environment variables (TRADIER_API_KEY, etc.)
5. Run dashboard with `--host 0.0.0.0`
6. Access via VPS public IP

**Security considerations:**
- Use HTTPS (Let's Encrypt)
- Add basic auth or IP whitelist
- Keep API keys secure

---

### Option 2: ngrok Tunnel (QUICKEST)
Expose local server to internet via tunnel

**Setup:**
```bash
# Install ngrok
snap install ngrok

# Authenticate (get authtoken from ngrok.com)
ngrok config add-authtoken YOUR_TOKEN

# Start tunnel
cd ~/.openclaw/workspace
python3 dashboard/scripts/serve_dashboard.py --host 0.0.0.0 --port 8765 &
ngrok http 8765
```

**Result:** Get public URL like `https://abc123.ngrok.io`

**Pros:** Free tier, instant setup
**Cons:** URL changes on restart, limited connections on free tier

---

### Option 3: Cloudflare Tunnel (FREE & STABLE)
More stable than ngrok, custom subdomain possible

**Setup:**
```bash
# Install cloudflared
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Authenticate
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create bazaar-dashboard

# Configure and run
cloudflared tunnel route dns bazaar-dashboard dashboard.yourdomain.com
cloudflared tunnel run bazaar-dashboard
```

**Pros:** Free, stable URL, Cloudflare CDN
**Cons:** Requires domain (can use free subdomain)

---

### Option 4: GitHub + GitHub Actions (CI/CD)
Automated deployment on every push

**Setup:**
1. Push code to GitHub repository
2. Create `.github/workflows/deploy.yml`
3. Configure secrets (API keys)
4. Auto-deploy to VPS on every commit

**Example workflow:**
```yaml
name: Deploy Dashboard
on: [push]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Deploy to VPS
        run: |
          ssh user@vps-ip "cd /app && git pull && pm2 restart dashboard"
```

---

## Recommended Approach

**For immediate use (today):**
1. Sign up at ngrok.com (free)
2. Install ngrok on your WSL machine
3. Run: `ngrok http 8765`
4. Access dashboard from anywhere via ngrok URL

**For long-term solution:**
1. Set up DigitalOcean Droplet ($5/month)
2. Deploy dashboard there
3. Configure HTTPS + basic auth
4. Access from anywhere reliably

## Security Checklist

- [ ] Use HTTPS (not HTTP)
- [ ] Add authentication (basic auth or OAuth)
- [ ] Restrict API key permissions (read-only where possible)
- [ ] Use environment variables for secrets
- [ ] Enable firewall (ufw) on VPS
- [ ] Regular security updates

## Next Steps

1. Choose deployment option
2. I can help configure the chosen solution
3. Test remote access
4. Document the setup for future reference

Which option would you like to pursue?
