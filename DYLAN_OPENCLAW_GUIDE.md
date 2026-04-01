# 🦞 Dylan's OpenClaw Quick Start Guide

## Welcome to Your AI Workspace!

**Your VM Details:**
- **VM Name:** dylan-catabolicsolutions
- **External IP:** 34.125.140.172
- **Zone:** us-west4-a
- **Access:** SSH via Google Cloud Console or gcloud

---

## Step 1: Access Your VM

### Option A: Browser SSH (Easiest)
1. Go to https://console.cloud.google.com/compute/instances
2. Find "dylan-catabolicsolutions"
3. Click **"SSH"** button
4. Terminal opens in browser

### Option B: gcloud CLI
```bash
gcloud compute ssh dylan-catabolicsolutions --zone=us-west4-a
```

### Option C: Regular SSH
```bash
ssh -i ~/.ssh/your_key dylan@34.125.140.172
```

---

## Step 2: First Time Setup

Once connected, run these commands:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Check if OpenClaw is installed
openclaw --version

# If not installed, install it:
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g openclaw

# Create your workspace
mkdir -p ~/.openclaw/workspace
cd ~/.openclaw/workspace

# Initialize OpenClaw
openclaw init
```

---

## Step 3: Start OpenClaw

```bash
# Configure to listen on all interfaces
openclaw config set gateway.bind 0.0.0.0

# Start the gateway
openclaw gateway start

# Check status
openclaw gateway status
```

**You should see:**
```
Gateway: running on http://0.0.0.0:18789
Dashboard: http://34.125.140.172:18789
```

---

## Step 4: Connect Your First AI

### Option 1: Web Chat (Simplest)
Open browser: `http://34.125.140.172:18789`

### Option 2: Telegram Bot
1. Message @BotFather on Telegram
2. Create new bot, get token
3. Run: `openclaw config set telegram.bot_token YOUR_TOKEN`
4. Start chatting with your bot

### Option 3: Discord Bot
1. Go to https://discord.com/developers/applications
2. Create new application → Bot
3. Copy token
4. Run: `openclaw config set discord.bot_token YOUR_TOKEN`
5. Invite bot to your server

---

## Step 5: Create Your AI Persona

In your workspace:
```bash
cd ~/.openclaw/workspace
```

Create these files:

**IDENTITY.md** - Who is your AI?
```markdown
- **Name:** [Your AI's name]
- **Creature:** [What type of AI]
- **Vibe:** [Personality traits]
- **Emoji:** [Favorite emoji]
```

**SOUL.md** - How should they behave?
```markdown
## Core Truths
- Be genuinely helpful
- Have opinions
- Be resourceful
- Remember you're a guest

## Vibe
[Describe personality]
```

**USER.md** - Who are they helping?
```markdown
- **Name:** Dylan
- **What to call them:** Dylan
- **Timezone:** America/Denver
- **Notes:** [Your preferences]
```

---

## Common Commands

```bash
# Check OpenClaw status
openclaw status

# View logs
openclaw logs

# Restart gateway
openclaw gateway restart

# Stop gateway
openclaw gateway stop

# Update OpenClaw
sudo npm update -g openclaw

# Check configuration
openclaw config get
```

---

## Troubleshooting

### "Command not found: openclaw"
```bash
# Reinstall
sudo npm install -g openclaw
```

### "Port 18789 already in use"
```bash
# Find and kill process
sudo lsof -ti:18789 | xargs sudo kill -9
# Then restart
openclaw gateway start
```

### "Permission denied"
```bash
# Fix permissions
sudo chown -R $USER:$USER ~/.openclaw
```

### Gateway won't start
```bash
# Check logs
openclaw logs

# Check if port is available
sudo ss -tlnp | grep 18789

# Try different port
openclaw config set gateway.port 18888
openclaw gateway start
```

### Can't access from browser
1. Check firewall rules in Google Cloud Console
2. Ensure port 18789 is open
3. Verify gateway is bound to 0.0.0.0 (not localhost)

---

## Getting Help

### From Ross (Your Brother):
- **Discord:** @ross_18600
- **Email:** [your email]
- **Emergency:** Call/text

### OpenClaw Resources:
- **Docs:** https://docs.openclaw.ai
- **GitHub:** https://github.com/openclaw/openclaw
- **Discord:** https://discord.com/invite/clawd

### Google Cloud Help:
- **Console:** https://console.cloud.google.com
- **SSH Issues:** Use browser-based SSH button
- **Billing:** Check quotas and limits

---

## Pro Tips

1. **Use `screen` or `tmux`** to keep sessions running
   ```bash
   sudo apt install -y screen
   screen -S openclaw
   openclaw gateway start
   # Press Ctrl+A then D to detach
   screen -r openclaw  # to reattach
   ```

2. **Set up auto-start on boot**
   ```bash
   # Create systemd service
   sudo tee /etc/systemd/system/openclaw.service << 'EOF'
   [Unit]
   Description=OpenClaw Gateway
   After=network.target

   [Service]
   Type=simple
   User=dylan
   ExecStart=/usr/bin/openclaw gateway start
   Restart=always

   [Install]
   WantedBy=multi-user.target
   EOF

   sudo systemctl enable openclaw
   sudo systemctl start openclaw
   ```

3. **Regular backups**
   ```bash
   # Backup workspace
   tar czf ~/openclaw-backup-$(date +%Y%m%d).tar.gz ~/.openclaw/workspace/
   ```

4. **Monitor resources**
   ```bash
   # Check CPU/memory
   htop

   # Check disk space
   df -h
   ```

---

## What Can You Build?

- **Personal AI Assistant** - Calendar, email, reminders
- **Discord/Telegram Bots** - Community management, games
- **Automation Scripts** - File organization, data processing
- **Trading Bots** (with Ross's help) - Market analysis, alerts
- **Home Automation** - Smart home integration
- **Creative Projects** - Storytelling, art generation

---

## Quick Reference Card

| Task | Command |
|------|---------|
| Start gateway | `openclaw gateway start` |
| Stop gateway | `openclaw gateway stop` |
| Check status | `openclaw status` |
| View logs | `openclaw logs` |
| Update | `sudo npm update -g openclaw` |
| Config | `openclaw config get/set` |
| SSH to VM | `gcloud compute ssh dylan-catabolicsolutions` |

---

## Your First Session Checklist

- [ ] SSH into VM
- [ ] Run `openclaw --version`
- [ ] Start gateway with `openclaw gateway start`
- [ ] Open browser to `http://34.125.140.172:18789`
- [ ] Create IDENTITY.md and SOUL.md
- [ ] Connect Telegram or Discord bot
- [ ] Send first message to your AI

---

**Welcome to the OpenClaw community, Dylan! 🦞**

*Questions? Stuck? Reach out to Ross anytime!*
