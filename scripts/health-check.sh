#!/bin/bash
# GrowthClaw health check — verifies tmux session is alive, restarts if dead.
# Install: cp to /etc/cron.d/growthclaw-health or add to crontab:
#   */5 * * * * /opt/growthclaw/scripts/health-check.sh

LOG_DIR="/var/log/growthclaw"
mkdir -p "$LOG_DIR"

if ! tmux has-session -t growthclaw 2>/dev/null; then
    echo "$(date): GrowthClaw tmux session dead, restarting..." >> "$LOG_DIR/health.log"
    systemctl restart growthclaw-agent
    echo "$(date): Restart triggered" >> "$LOG_DIR/health.log"
fi
