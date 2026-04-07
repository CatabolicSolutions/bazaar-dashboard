#!/bin/bash
# Install ETH Scalper as a systemd service

echo "Installing ETH Scalper systemd service..."

# Copy service file
cp /var/www/bazaar/eth_scalper/eth-scalper.service /etc/systemd/system/

# Reload systemd
daemon-reload

# Enable service to start on boot
systemctl enable eth-scalper.service

# Start the service
systemctl start eth-scalper.service

echo "Service installed and started!"
echo ""
echo "Commands:"
echo "  systemctl status eth-scalper    - Check status"
echo "  systemctl stop eth-scalper      - Stop bot"
echo "  systemctl start eth-scalper     - Start bot"
echo "  systemctl restart eth-scalper   - Restart bot"
echo "  journalctl -u eth-scalper -f    - View logs"
