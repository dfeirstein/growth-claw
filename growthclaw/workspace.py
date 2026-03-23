"""GrowthClaw workspace management — creates and manages customer workspaces separate from source code."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

WORKSPACE_MARKER = ".growthclaw-workspace"
ENV_TEMPLATE = """# ═══════════════════════════════════════════════════════════════
# GrowthClaw Configuration
# ═══════════════════════════════════════════════════════════════

# ─── Database ─────────────────────────────────────────────────
# Customer database (READ ONLY — GrowthClaw discovers your schema)
CUSTOMER_DATABASE_URL=postgresql://user:password@host:5432/dbname

# GrowthClaw internal database (stores triggers, journeys, experiments)
# Can be same DB (uses growthclaw schema) or a separate DB
GROWTHCLAW_DATABASE_URL=postgresql://user:password@host:5432/dbname

# ─── LLM Provider (at least one required) ────────────────────
ANTHROPIC_API_KEY=
# NVIDIA_API_KEY=
# NVIDIA_NIM_URL=                          # Local GPU: http://localhost:8000/v1

# ─── SMS (Twilio) ────────────────────────────────────────────
# TWILIO_ACCOUNT_SID=
# TWILIO_AUTH_TOKEN=
# TWILIO_FROM_NUMBER=

# ─── Email ────────────────────────────────────────────────────
GROWTHCLAW_EMAIL_PROVIDER=resend
# RESEND_API_KEY=
# SENDGRID_API_KEY=                        # Use instead if provider=sendgrid
# GROWTHCLAW_FROM_EMAIL=hello@yourbusiness.com
# GROWTHCLAW_FROM_NAME=

# ─── Business Context (helps LLM understand your data) ───────
GROWTHCLAW_BUSINESS_NAME=
GROWTHCLAW_BUSINESS_DESCRIPTION=

# ─── Settings ─────────────────────────────────────────────────
GROWTHCLAW_DRY_RUN=true
GROWTHCLAW_CARD_LINK_URL=https://app.example.com
GROWTHCLAW_SAMPLE_ROWS=500
GROWTHCLAW_MAX_FIRES_PER_TRIGGER=3
GROWTHCLAW_COOLDOWN_HOURS=24
GROWTHCLAW_QUIET_HOURS_START=21
GROWTHCLAW_QUIET_HOURS_END=8

# ─── Frequency Caps ──────────────────────────────────────────
GROWTHCLAW_MAX_SMS_PER_DAY=2
GROWTHCLAW_MAX_SMS_PER_WEEK=5
GROWTHCLAW_MAX_EMAIL_PER_DAY=2
GROWTHCLAW_MAX_EMAIL_PER_WEEK=7

# ─── Memory (optional — for AutoResearch learning) ───────────
# OPENAI_API_KEY=                          # For embeddings (text-embedding-3-small)
"""

CLAUDE_MD_TEMPLATE = """# GrowthClaw Agent

You are the GrowthClaw AI marketing agent for {business_name}.

## What You Do
- Monitor real-time customer events via PostgreSQL CDC triggers
- Build 360° customer profiles and compose personalized outreach (SMS + email)
- Run autonomous A/B experiments (AutoResearch) to optimize messaging
- Track outcomes and learn from results via semantic memory

## Available MCP Tools
Use these tools to answer operator questions and manage the system:
- `gc_status` — System health check
- `gc_triggers_list` — All triggers with performance metrics
- `gc_triggers_approve` / `gc_triggers_pause` — Manage triggers
- `gc_journeys` — Recent outreach log
- `gc_experiments` — AutoResearch cycle results
- `gc_metrics` — Key dashboard metrics (funnel, sends, conversions)
- `gc_memory_recall` — Search past learnings and patterns
- `gc_memory_store` — Save a new pattern, guardrail, or insight
- `gc_llm_usage` — LLM usage stats and costs

## How to Respond
- Format metrics in markdown tables
- Highlight conversion rates, trends, and anomalies
- Reference AutoResearch learnings when suggesting experiments
- Be concise — operators want quick answers
"""

GITIGNORE_TEMPLATE = """# GrowthClaw workspace
.env
data/
*.log
__pycache__/
"""


def find_workspace(start: Path | None = None) -> Path | None:
    """Walk up from start (or cwd) looking for a .growthclaw-workspace marker."""
    current = start or Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / WORKSPACE_MARKER).exists():
            return parent
    return None


def is_workspace(path: Path) -> bool:
    """Check if a path is a GrowthClaw workspace."""
    return (path / WORKSPACE_MARKER).exists()


def init_workspace(path: str | Path, business_name: str = "") -> Path:
    """Create a new GrowthClaw workspace directory.

    Creates:
        <path>/
        ├── .growthclaw-workspace   # Marker file
        ├── .env                    # Configuration (customer fills in)
        ├── .gitignore              # Excludes secrets and data
        ├── .mcp.json               # MCP server config
        ├── .claude/
        │   └── settings.json       # Permissions (empty, filled by setup)
        ├── CLAUDE.md               # Agent context
        └── data/
            ├── memory/             # LanceDB storage
            └── logs/               # Tool call and notification logs
    """
    workspace = Path(path).expanduser().resolve()

    if workspace.exists() and any(workspace.iterdir()):
        if is_workspace(workspace):
            print(f"  Workspace already exists at {workspace}")
            return workspace
        # Non-empty non-workspace directory
        raise FileExistsError(f"Directory {workspace} exists and is not a GrowthClaw workspace")

    workspace.mkdir(parents=True, exist_ok=True)

    # Marker file
    (workspace / WORKSPACE_MARKER).write_text("growthclaw workspace\nversion: 0.2.0\n")

    # .env
    (workspace / ".env").write_text(ENV_TEMPLATE)

    # .gitignore
    (workspace / ".gitignore").write_text(GITIGNORE_TEMPLATE)

    # CLAUDE.md
    name = business_name or "your business"
    (workspace / "CLAUDE.md").write_text(CLAUDE_MD_TEMPLATE.format(business_name=name))

    # .claude/settings.json (empty — filled by setup wizard)
    claude_dir = workspace / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (claude_dir / "settings.json").write_text("{}\n")

    # .mcp.json — points to the installed growthclaw package
    python_path = shutil.which("python3") or shutil.which("python") or sys.executable
    mcp_config = {
        "mcpServers": {
            "growthclaw": {
                "command": python_path,
                "args": ["-m", "growthclaw.mcp_server"],
                "cwd": str(workspace),
            }
        }
    }
    (workspace / ".mcp.json").write_text(json.dumps(mcp_config, indent=2) + "\n")

    # Data directories
    (workspace / "data" / "memory").mkdir(parents=True, exist_ok=True)
    (workspace / "data" / "logs").mkdir(parents=True, exist_ok=True)

    return workspace


def get_workspace_or_exit() -> Path:
    """Find the workspace or print an error and exit."""
    ws = find_workspace()
    if ws is None:
        print("ERROR: Not in a GrowthClaw workspace.")
        print()
        print("  Create one with: growthclaw init <path>")
        print("  Example: growthclaw init ~/my-company")
        sys.exit(1)
    return ws
