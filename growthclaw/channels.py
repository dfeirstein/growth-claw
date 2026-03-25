"""GrowthClaw channel setup — configures Claude Code Channels for operator communication."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def _get_workspace() -> Path:
    """Get the workspace directory (~/.growthclaw/)."""
    from growthclaw.workspace import get_workspace

    return get_workspace()


def _get_mcp_config() -> Path:
    return _get_workspace() / ".mcp.json"


def setup_telegram() -> None:
    """Interactive setup for Telegram channel with Claude Code."""
    print()
    print("  Telegram Channel Setup")
    print("  ─────────────────────")
    print()
    print("  This connects your Telegram bot to the GrowthClaw agent,")
    print("  so you can chat with GrowthClaw from your phone.")
    print()

    # Check prerequisites
    if not shutil.which("claude"):
        print("  ERROR: Claude Code CLI is required.")
        print("  Install: npm install -g @anthropic-ai/claude-code")
        return

    print("  Step 1: Create a Telegram bot")
    print("  ───────────────────────────────")
    print("  1. Open Telegram and message @BotFather")
    print("  2. Send /newbot")
    print("  3. Name it: GrowthClaw Agent (or your preferred name)")
    print("  4. Copy the bot token")
    print()

    token = input("  Paste your Telegram bot token: ").strip()
    if not token:
        print("  Cancelled.")
        return

    print()
    print("  Step 2: Configuring Claude Code Channel...")

    # Claude Code channels are configured via the CLI
    # The user needs to run: claude channel add telegram --token <token>
    print()
    print("  Run this command to connect Telegram:")
    print(f"  claude channel add telegram --token {token}")
    print()
    print("  Once connected, message your bot on Telegram.")
    print("  Claude Code will receive messages and can use GrowthClaw MCP tools.")
    print()


def setup_discord() -> None:
    """Interactive setup for Discord channel with Claude Code."""
    print()
    print("  Discord Channel Setup")
    print("  ─────────────────────")
    print()
    print("  This connects a Discord bot to the GrowthClaw agent.")
    print()
    print("  Step 1: Create a Discord bot")
    print("  ─────────────────────────────")
    print("  1. Go to https://discord.com/developers/applications")
    print("  2. Click 'New Application' → name it 'GrowthClaw'")
    print("  3. Go to Bot → click 'Add Bot'")
    print("  4. Copy the bot token")
    print("  5. Go to OAuth2 → URL Generator")
    print("     - Scopes: bot, applications.commands")
    print("     - Bot Permissions: Send Messages, Read Message History")
    print("  6. Use the generated URL to invite the bot to your server")
    print()

    token = input("  Paste your Discord bot token: ").strip()
    if not token:
        print("  Cancelled.")
        return

    print()
    print("  Run this command to connect Discord:")
    print(f"  claude channel add discord --token {token}")
    print()


def setup_mcp() -> None:
    """Set up the GrowthClaw MCP server for Claude Code."""
    print()
    print("  MCP Server Setup")
    print("  ────────────────")
    print()

    cwd = Path.cwd()
    python_path = sys.executable

    mcp_config = {}
    if _get_mcp_config().exists():
        try:
            mcp_config = json.loads(_get_mcp_config().read_text())
        except json.JSONDecodeError:
            pass

    if "mcpServers" not in mcp_config:
        mcp_config["mcpServers"] = {}

    mcp_config["mcpServers"]["growthclaw"] = {
        "command": python_path,
        "args": ["-m", "growthclaw.mcp_server"],
        "cwd": str(cwd),
    }

    _get_mcp_config().write_text(json.dumps(mcp_config, indent=2) + "\n")
    print(f"  Written to: {_get_mcp_config()}")
    print()
    print("  GrowthClaw MCP server registered. Claude Code will now have access to:")
    print("  - gc_status, gc_triggers_list, gc_triggers_approve, gc_triggers_pause")
    print("  - gc_journeys, gc_experiments, gc_metrics")
    print("  - gc_memory_recall, gc_memory_store")
    print("  - gc_llm_usage")
    print()
    print("  Restart Claude Code to pick up the new MCP server.")


def setup_skill() -> None:
    """Install the GrowthClaw skill for Claude Code."""
    print()
    print("  Skill Installation")
    print("  ──────────────────")
    print()

    skill_source = Path(__file__).parent / "skill.md"
    skill_dest = Path.home() / ".claude" / "skills" / "growthclaw.md"

    if not skill_source.exists():
        print("  ERROR: skill.md not found in growthclaw package.")
        return

    skill_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_source, skill_dest)

    print(f"  Installed to: {skill_dest}")
    print("  Claude Code will now know how to use GrowthClaw tools.")


def setup_permissions(mode: str = "recommended") -> None:
    """Generate Claude Code permissions based on chosen mode."""
    print()
    print("  Permission Configuration")
    print("  ────────────────────────")
    print()

    workspace = _get_workspace()
    project_settings = workspace / ".claude" / "settings.json"
    project_settings.parent.mkdir(parents=True, exist_ok=True)

    # Copy hooks from installed package to workspace
    hooks_dest = workspace / "hooks"
    hooks_dest.mkdir(exist_ok=True)
    hooks_source = Path(__file__).parent / "hooks"
    if hooks_source.exists():
        for hook_file in hooks_source.glob("*.py"):
            shutil.copy2(hook_file, hooks_dest / hook_file.name)

    # Use the workspace venv python and workspace hooks path
    python_path = str(workspace / ".venv" / "bin" / "python3")
    if not Path(python_path).exists():
        python_path = sys.executable
    hook_script = str(hooks_dest / "post_tool_use.py")

    if mode == "recommended":
        settings = {
            "permissions": {
                "allow": [
                    "Read",
                    "Glob",
                    "Grep",
                    "WebFetch",
                    "WebSearch",
                    "mcp__growthclaw__*",
                    "Bash(python -m growthclaw.*)",
                    "Bash(growthclaw *)",
                    "Bash(cat *)",
                    "Bash(ls *)",
                    "Bash(git status)",
                    "Bash(git log *)",
                ],
                "deny": [
                    "Bash(rm -rf *)",
                    "Bash(sudo *)",
                    "Bash(curl * | bash)",
                ],
            },
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "mcp__growthclaw__*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"{python_path} {hook_script}",
                            }
                        ],
                    }
                ],
                "PermissionRequest": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": 'echo \'{"hookSpecificOutput":{"permissionDecision":"allow"}}\'',
                            }
                        ],
                    }
                ],
            },
        }
        print("  Mode: Recommended")
        print("  - All GrowthClaw tools auto-approved")
        print("  - Unknown actions auto-approved (agent never blocks)")
        print("  - Dangerous commands denied (rm -rf, sudo)")

    elif mode == "strict":
        settings = {
            "permissions": {
                "allow": [
                    "Read",
                    "Glob",
                    "Grep",
                    "mcp__growthclaw__*",
                ],
                "deny": [
                    "Bash(rm -rf *)",
                    "Bash(sudo *)",
                ],
            },
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "mcp__growthclaw__*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"{python_path} {hook_script}",
                            }
                        ],
                    }
                ],
            },
        }
        print("  Mode: Strict")
        print("  - GrowthClaw MCP tools auto-approved")
        print("  - Other actions require operator approval")

    elif mode == "full":
        settings = {}
        print("  Mode: Full Autonomy")
        print("  - All permission checks skipped")
        print("  - Use only in sandboxed environments")

    else:
        print(f"  Unknown mode: {mode}")
        return

    project_settings.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"\n  Written to: {project_settings}")


def interactive_setup() -> None:
    """Interactive channel and agent setup wizard."""
    print()
    print("═══════════════════════════════════════════")
    print("  GrowthClaw Agent Setup Wizard")
    print("═══════════════════════════════════════════")
    print()

    # Step 1: MCP server
    print("  [1/4] MCP Server")
    setup_mcp()

    # Step 2: Skill
    print("  [2/4] Claude Code Skill")
    setup_skill()

    # Step 3: Permission mode
    print("  [3/4] Permission Mode")
    print()
    print("  How autonomous should the agent be?")
    print()
    print("  1. Recommended — Agent never blocks. Dangerous commands denied.")
    print("  2. Strict — GrowthClaw tools only. Other actions need approval.")
    print("  3. Full autonomy — No permission checks (sandboxed environments only).")
    print()
    choice = input("  Select [1/2/3] (default: 1): ").strip() or "1"
    mode_map = {"1": "recommended", "2": "strict", "3": "full"}
    setup_permissions(mode_map.get(choice, "recommended"))

    # Step 4: Channels
    print()
    print("  [4/4] Operator Channels (optional)")
    print()
    print("  Connect a messaging channel so you can chat with GrowthClaw from your phone.")
    print()
    print("  1. Telegram")
    print("  2. Discord")
    print("  3. Skip (configure later)")
    print()
    ch = input("  Select [1/2/3] (default: 3): ").strip() or "3"
    if ch == "1":
        setup_telegram()
    elif ch == "2":
        setup_discord()
    else:
        print("  Skipped. You can set up channels later with: growthclaw channels add")

    print()
    print("═══════════════════════════════════════════")
    print("  Setup Complete!")
    print("═══════════════════════════════════════════")
    print()
    print("  Start the agent:")
    print("    growthclaw daemon start --claude    # Claude Code in tmux")
    print("    growthclaw daemon start             # Standalone (CDC + scheduler)")
    print()
    print("  Attach to the agent:")
    print("    tmux attach -t growthclaw")
    print()
