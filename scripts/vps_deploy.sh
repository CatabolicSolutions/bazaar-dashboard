#!/bin/bash
# VPS Deployment Script for Bazaar Dashboard
# Run this on your fresh Ubuntu 22.04 VPS

set -e

echo "=== Bazaar Dashboard VPS Setup ==="

# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y nodejs npm python3 python3-pip nginx git certbot python3-certbot-nginx

# Install PM2 globally
sudo npm install -g pm2

# Create app directory
sudo mkdir -p /var/www/bazaar
sudo chown $USER:$USER /var/www/bazaar

# Clone repository (you'll need to set this up)
echo "Please clone your repository to /var/www/bazaar"
echo "Or use: git clone https://github.com/yourusername/bazaar-dashboard.git /var/www/bazaar"

# Set up Python environment
cd /var/www/bazaar
python3 -m pip install -r requirements.txt 2>/dev/null || echo "No requirements.txt found"

# Create environment file
cat > /var/www/bazaar/.env << 'EOF'
TRADIER_API_KEY=your_api_key_here
TRADIER_ACCOUNT_ID=your_account_id
TRADIER_LIVE_ACCOUNT_ID=your_account_id
EOF

echo "Environment file created. Please edit /var/www/bazaar/.env with your actual API keys"

# Set up PM2 ecosystem
cat > /var/www/bazaar/ecosystem.config.js << 'EOF'
module.exports = {
  apps: [{
    name: 'bazaar-dashboard',
    script: 'dashboard/scripts/serve_dashboard.py',
    args: '--host 0.0.0.0 --port 8765',
    cwd: '/var/www/bazaar',
    env: {
      NODE_ENV: 'production',
      PYTHONUNBUFFERED: '1'
    },
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    log_file: '/var/log/bazaar/dashboard.log',
    out_file: '/var/log/bazaar/dashboard.out.log',
    error_file: '/var/log/bazaar/dashboard.error.log',
    time: true
  }]
};
EOF

# Create log directory
sudo mkdir -p /var/log/bazaar
sudo chown $USER:$USER /var/log/bazaar

echo "=== Nginx Setup ==="

# Create nginx config
cat > /tmp/bazaar-nginx.conf << 'EOF'
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

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=dashboard:10m rate=10r/s;
    limit_req zone=dashboard burst=20 nodelay;
}
EOF

echo "Nginx config created at /tmp/bazaar-nginx.conf"
echo "Copy it to: sudo cp /tmp/bazaar-nginx.conf /etc/nginx/sites-available/bazaar"
echo "Then: sudo ln -s /etc/nginx/sites-available/bazaar /etc/nginx/sites-enabled/"

echo "=== SSL Certificate ==="
echo "After DNS is configured, run:"
echo "sudo certbot --nginx -d dashboard.yourdomain.com"

echo "=== Firewall Setup ==="
echo "sudo ufw allow 'Nginx Full'"
echo "sudo ufw allow OpenSSH"
echo "sudo ufw enable"

echo "=== Deployment Complete ==="
echo ""
echo "Next steps:"
echo "1. Clone your repository to /var/www/bazaar"
echo "2. Edit /var/www/bazaar/.env with API keys"
echo "3. Update DNS: dashboard.yourdomain.com -> VPS_IP"
echo "4. Run: pm2 start ecosystem.config.js"
echo "5. Run: sudo certbot --nginx -d dashboard.yourdomain.com"
echo ""
echo "Dashboard will be available at: https://dashboard.yourdomain.com"
