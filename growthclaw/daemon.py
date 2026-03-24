"""GrowthClaw daemon — manages the always-on agent process (tmux + Claude Code or standalone)."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import signal
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("growthclaw.daemon")

GROWTHCLAW_HOME = Path.home() / ".growthclaw"
PID_FILE = GROWTHCLAW_HOME / "daemon.pid"
TMUX_SESSION = "growthclaw"
LOG_DIR = GROWTHCLAW_HOME / "data" / "logs"


def _ensure_dirs() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def is_running() -> bool:
    """Check if the GrowthClaw daemon is running."""
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)  # Check if process exists
        return True
    except (ProcessLookupError, ValueError):
        PID_FILE.unlink(missing_ok=True)
        return False


def _tmux_session_exists() -> bool:
    """Check if the growthclaw tmux session exists."""
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", TMUX_SESSION],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def start(mode: str = "standalone", resume: bool = True) -> None:
    """Start the GrowthClaw daemon.

    Modes:
    - standalone: Run GrowthClaw CDC listener + scheduler directly (no Claude Code)
    - claude: Run Claude Code CLI in a tmux session with GrowthClaw MCP tools
    """
    _ensure_dirs()

    if is_running():
        print("GrowthClaw daemon is already running.")
        print(f"  PID: {PID_FILE.read_text().strip()}")
        if _tmux_session_exists():
            print(f"  tmux: attach with `tmux attach -t {TMUX_SESSION}`")
        return

    if mode == "claude":
        _start_claude_mode(resume)
    else:
        _start_standalone_mode()


def _start_standalone_mode() -> None:
    """Start GrowthClaw as a standalone background process (CDC + scheduler)."""
    print("Starting GrowthClaw daemon (standalone mode)...")

    # Fork to background
    cmd = [sys.executable, "-m", "growthclaw.cli", "start"]
    log_file = LOG_DIR / "daemon.log"

    with open(log_file, "a") as log:
        proc = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

    PID_FILE.write_text(str(proc.pid))
    print(f"  PID: {proc.pid}")
    print(f"  Log: {log_file}")
    print("  Stop: growthclaw daemon stop")


def _start_claude_mode(resume: bool = True) -> None:
    """Start Claude Code CLI in a tmux session with GrowthClaw MCP tools."""
    if not shutil.which("tmux"):
        print("ERROR: tmux is required for claude mode.")
        print("  Install: brew install tmux (macOS) or apt install tmux (Linux)")
        sys.exit(1)

    if not shutil.which("claude"):
        print("ERROR: Claude Code CLI is required for claude mode.")
        print("  Install: npm install -g @anthropic-ai/claude-code")
        sys.exit(1)

    if _tmux_session_exists():
        print(f"tmux session '{TMUX_SESSION}' already exists.")
        print(f"  Attach: tmux attach -t {TMUX_SESSION}")
        return

    print("Starting GrowthClaw agent (Claude Code in tmux)...")

    # Build the claude command — runs in ~/.growthclaw/ workspace
    workspace = str(GROWTHCLAW_HOME)

    # Only use --resume if there are existing conversations
    resume_flag = ""
    if resume:
        claude_projects = Path.home() / ".claude" / "projects"
        if claude_projects.exists() and any(claude_projects.iterdir()):
            resume_flag = "--resume"

    claude_cmd = f"cd {workspace} && claude {resume_flag}"

    # Start tmux session
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", TMUX_SESSION, claude_cmd],
        check=True,
    )

    # Get the tmux server PID for tracking
    result = subprocess.run(
        ["tmux", "display-message", "-t", TMUX_SESSION, "-p", "#{pid}"],
        capture_output=True,
        text=True,
    )
    pid = result.stdout.strip() or "unknown"
    PID_FILE.write_text(pid)

    print(f"  tmux session: {TMUX_SESSION}")
    print(f"  Attach: tmux attach -t {TMUX_SESSION}")
    print("  Stop: growthclaw daemon stop")
    print()
    print("The agent is running. You can:")
    print("  - Attach to the session to chat with the agent")
    print("  - Connect via Telegram/Discord (if channels configured)")
    print("  - Use Remote Control from your phone via claude.ai/code")


def stop() -> None:
    """Stop the GrowthClaw daemon."""
    _ensure_dirs()

    if _tmux_session_exists():
        print(f"Stopping tmux session '{TMUX_SESSION}'...")
        # Send /exit to Claude Code first
        subprocess.run(
            ["tmux", "send-keys", "-t", TMUX_SESSION, "/exit", "Enter"],
            capture_output=True,
        )
        import time

        time.sleep(2)
        # Kill the session
        subprocess.run(["tmux", "kill-session", "-t", TMUX_SESSION], capture_output=True)
        print("  tmux session stopped.")

    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"  Process {pid} stopped.")
        except (ProcessLookupError, ValueError):
            pass
        PID_FILE.unlink(missing_ok=True)
    else:
        if not _tmux_session_exists():
            print("GrowthClaw daemon is not running.")

    print("GrowthClaw daemon stopped.")


def status() -> None:
    """Show daemon status."""
    _ensure_dirs()

    running = is_running()
    tmux = _tmux_session_exists()

    print(f"  Daemon running: {'yes' if running else 'no'}")
    if PID_FILE.exists():
        print(f"  PID: {PID_FILE.read_text().strip()}")
    print(f"  tmux session: {'active' if tmux else 'none'}")
    print(f"  Platform: {platform.system()} {platform.machine()}")
    print(f"  Log dir: {LOG_DIR}")

    if tmux:
        print(f"\n  Attach: tmux attach -t {TMUX_SESSION}")
