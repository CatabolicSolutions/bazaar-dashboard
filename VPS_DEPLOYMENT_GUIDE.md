# VPS Deployment Guide - Bazaar Dashboard

## Overview
Deploy the Bazaar Dashboard to a VPS for 24/7 remote access from anywhere.

## Prerequisites
- Domain name (Google Workspace domain recommended)
- VPS with Ubuntu 22.04 (DigitalOcean, AWS, Linode, etc.)
- SSH access to VPS
- Tradier API credentials

---

## Step 1: Provision VPS

### DigitalOcean (Recommended)
1. Sign up at https://digitalocean.com
2. Create Droplet:
   - Image: Ubuntu 22.04 (LTS) x64
   - Plan: Basic ($6/month - 1GB RAM, 1 CPU)
   - Datacenter: Choose closest to you
   - Authentication: SSH key (recommended)
3. Note the IP address

### AWS EC2 (Alternative)
1. Sign up at https://aws.amazon.com
2. Launch EC2 instance:
   - AMI: Ubuntu Server 22.04 LTS
   - Instance type: t2.micro (free tier eligible)
   - Security group: Allow HTTP (80), HTTPS (443), SSH (22)
3. Note the public IP

---

## Step 2: Configure DNS

In your Google Workspace domain admin:

1. Go to Domains → DNS
2. Add A record:
   - Name: `dashboard` (or subdomain of choice)
   - Type: A
   - TTL: 3600
   - Data: [Your VPS IP address]
3. Wait 5-10 minutes for propagation

Verify: `dig dashboard.yourdomain.com`

---

## Step 3: Run Deployment Script

SSH into your VPS:
```bash
ssh root@your-vps-ip
```

Download and run deployment script:
```bash
curl -O https://raw.githubusercontent.com/yourusername/bazaar-dashboard/main/scripts/vps_deploy.sh
chmod +x vps_deploy.sh
./vps_deploy.sh
```

Or manually:
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y nodejs npm python3 python3-pip nginx git certbot python3-certbot-nginx

# Install PM2
sudo npm install -g pm2

# Create app directory
sudo mkdir -p /var/www/bazaar
sudo chown $USER:$USER /var/www/bazaar
```

---

## Step 4: Deploy Application

### Clone Repository
```bash
cd /var/www/bazaar
git clone https://github.com/yourusername/bazaar-dashboard.git .
```

### Set Environment Variables
```bash
cat > .env << 'EOF'
TRADIER_API_KEY=your_actual_api_key
TRADIER_ACCOUNT_ID=your_account_id
TRADIER_LIVE_ACCOUNT_ID=your_account_id
EOF
```

### Configure Nginx
```bash
sudo tee /etc/nginx/sites-available/bazaar << 'EOF'
server {
    listen 80;
    server_name dashboard.yourdomain.com;

    location / {
        proxy_pass http://localhost:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/bazaar /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Start Dashboard with PM2
```bash
cd /var/www/bazaar
pm2 start dashboard/scripts/serve_dashboard.py --name bazaar-dashboard -- --host 0.0.0.0 --port 8765
pm2 save
pm2 startup
```

---

## Step 5: Enable HTTPS (SSL)

```bash
sudo certbot --nginx -d dashboard.yourdomain.com
```

Follow prompts:
- Enter email
- Agree to terms
- Choose redirect HTTP to HTTPS (recommended)

Test auto-renewal:
```bash
sudo certbot renew --dry-run
```

---

## Step 6: Configure Firewall

```bash
sudo ufw allow 'Nginx Full'
sudo ufw allow OpenSSH
sudo ufw enable
```

---

## Step 7: Verify Deployment

1. **Check dashboard is running:**
   ```bash
   pm2 status
   ```

2. **Test local access:**
   ```bash
   curl http://localhost:8765/app
   ```

3. **Test remote access:**
   Open browser: `https://dashboard.yourdomain.com`

---

## Step 8: Setup CI/CD (Optional but Recommended)

### GitHub Secrets
Add these secrets to your GitHub repository:
- `VPS_HOST`: Your VPS IP address
- `VPS_USER`: Username (usually root or ubuntu)
- `VPS_SSH_KEY`: Private SSH key for deployment

### Deploy Key
On VPS:
```bash
ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/github_deploy
cat ~/.ssh/github_deploy.pub
```

Add public key to GitHub repo → Settings → Deploy keys

Add private key to GitHub Secrets as `VPS_SSH_KEY`

---

## Maintenance

### Update Dashboard
```bash
ssh root@your-vps-ip
cd /var/www/bazaar
git pull
pm2 restart bazaar-dashboard
```

### View Logs
```bash
pm2 logs bazaar-dashboard
# OR
tail -f /var/log/bazaar/dashboard.log
```

### Monitor Resources
```bash
pm2 monit
htop
```

### Backup
```bash
# Backup journal
tar czf ~/bazaar-backup-$(date +%Y%m%d).tar.gz /var/www/bazaar/journal/
```

---

## Security Checklist

- [ ] Firewall enabled (ufw)
- [ ] SSH key authentication only (no password)
- [ ] HTTPS enabled (Let's Encrypt)
- [ ] API keys in environment variables (not in code)
- [ ] Regular security updates: `sudo apt update && sudo apt upgrade`
- [ ] Fail2ban installed for intrusion prevention
- [ ] Log monitoring configured

---

## Troubleshooting

### Dashboard not accessible
```bash
# Check if running
pm2 status

# Check logs
pm2 logs

# Check nginx
sudo nginx -t
sudo systemctl status nginx
```

### SSL certificate issues
```bash
sudo certbot renew --force-renewal
sudo systemctl restart nginx
```

### High memory usage
```bash
# Restart to clear memory
pm2 restart bazaar-dashboard

# Add swap if needed
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

## Cost Estimate

| Component | Monthly Cost |
|-----------|-------------|
| DigitalOcean Droplet (1GB) | $6 |
| Domain (if new) | $10-15/year |
| **Total** | **~$6-7/month** |

---

## Next Steps for Crypto Trading

Once VPS is deployed:
1. Add crypto exchange API integrations
2. Set up additional trading bots
3. Configure multi-exchange arbitrage
4. Add crypto-specific risk management

The VPS infrastructure will support all future trading developments.
