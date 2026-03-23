#!/usr/bin/env python3
"""Claude Code hook: handles GrowthClaw notifications (conversions, experiment completions, errors)."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / ".growthclaw" / "logs"
NOTIFICATION_LOG = LOG_DIR / "notifications.jsonl"


def main() -> None:
    """Read notification event from stdin and log it."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    try:
        event_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception):
        return

    notification_type = event_data.get("type", "")
    message = event_data.get("message", "")

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": notification_type,
        "message": message,
    }

    with open(NOTIFICATION_LOG, "a") as f:
        f.write(json.dumps(log_entry) + "\n")


if __name__ == "__main__":
    main()
