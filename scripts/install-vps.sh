#!/bin/bash
# GrowthClaw VPS Installation Script
# Usage: curl -sSL https://raw.githubusercontent.com/dfeirstein/growth-claw/main/scripts/install-vps.sh | bash
# Or: bash scripts/install-vps.sh

set -e

INSTALL_DIR="/opt/growthclaw"
GROWTHCLAW_USER="growthclaw"

echo "================================================"
echo "  GrowthClaw VPS Installation"
echo "================================================"

# Check for required tools
for cmd in python3 pip3 git tmux; do
    if ! command -v $cmd &> /dev/null; then
        echo "ERROR: $cmd is required but not installed."
        echo "Install with: sudo apt install python3 python3-pip python3-venv git tmux"
        exit 1
    fi
done

# Create growthclaw user if needed
if ! id "$GROWTHCLAW_USER" &>/dev/null; then
    echo "Creating user: $GROWTHCLAW_USER"
    sudo useradd -m -s /bin/bash "$GROWTHCLAW_USER"
fi

# Clone or pull repo
if [ -d "$INSTALL_DIR" ]; then
    echo "Updating existing installation..."
    cd "$INSTALL_DIR"
    sudo -u "$GROWTHCLAW_USER" git pull
else
    echo "Cloning GrowthClaw..."
    sudo git clone https://github.com/dfeirstein/growth-claw.git "$INSTALL_DIR"
    sudo chown -R "$GROWTHCLAW_USER:$GROWTHCLAW_USER" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# Create virtual environment and install
echo "Setting up Python environment..."
sudo -u "$GROWTHCLAW_USER" python3 -m venv .venv
sudo -u "$GROWTHCLAW_USER" .venv/bin/pip install -e .

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env from template..."
    sudo -u "$GROWTHCLAW_USER" cp .env.example .env
    echo ""
    echo "IMPORTANT: Edit /opt/growthclaw/.env with your real credentials:"
    echo "  sudo -u $GROWTHCLAW_USER nano $INSTALL_DIR/.env"
    echo ""
fi

# Run migrations
echo "Running database migrations..."
sudo -u "$GROWTHCLAW_USER" .venv/bin/python -m growthclaw.cli migrate

# Install systemd service
echo "Installing systemd service..."
sudo cp growthclaw/growthclaw-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable growthclaw-agent

# Install health check cron
echo "Installing health check cron..."
echo "*/5 * * * * $GROWTHCLAW_USER $INSTALL_DIR/scripts/health-check.sh" | sudo tee /etc/cron.d/growthclaw-health > /dev/null

# Create log directory
sudo mkdir -p /var/log/growthclaw
sudo chown "$GROWTHCLAW_USER:$GROWTHCLAW_USER" /var/log/growthclaw

echo ""
echo "================================================"
echo "  Installation Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "  1. Edit credentials:  sudo -u $GROWTHCLAW_USER nano $INSTALL_DIR/.env"
echo "  2. Run onboarding:    sudo -u $GROWTHCLAW_USER $INSTALL_DIR/.venv/bin/growthclaw onboard"
echo "  3. Start the agent:   sudo systemctl start growthclaw-agent"
echo "  4. Check status:      sudo systemctl status growthclaw-agent"
echo "  5. View logs:         sudo journalctl -u growthclaw-agent -f"
echo ""
