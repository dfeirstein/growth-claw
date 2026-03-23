#!/usr/bin/env python3
"""Claude Code hook: logs all GrowthClaw MCP tool calls for observability."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / ".growthclaw" / "logs"
LOG_FILE = LOG_DIR / "tool_calls.jsonl"


def main() -> None:
    """Read hook event from stdin and log GrowthClaw tool calls."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    try:
        event_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception):
        return

    tool_name = event_data.get("tool_name", "")
    if not tool_name.startswith("mcp__growthclaw__"):
        return

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "tool": tool_name.replace("mcp__growthclaw__", ""),
        "input": event_data.get("tool_input", {}),
        "session_id": event_data.get("session_id", ""),
    }

    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(log_entry) + "\n")


if __name__ == "__main__":
    main()
