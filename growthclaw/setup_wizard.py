"""GrowthClaw setup wizard — interactive onboarding that collects credentials and configures the workspace."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def run_wizard(workspace: Path) -> None:
    """Interactive setup wizard that runs after `growthclaw init`.

    Collects:
    1. Database connection strings
    2. LLM API keys (Anthropic / NVIDIA)
    3. Business context
    4. SMS / Email provider keys (optional)
    5. Claude Code login verification
    6. Channel setup (Telegram / Discord)
    7. Permission mode selection
    """
    env_path = workspace / ".env"
    env_lines: dict[str, str] = {}

    # Load existing .env as base
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                env_lines[key.strip()] = val.strip()

    print()
    print("═══════════════════════════════════════════════════════")
    print("  GrowthClaw Setup Wizard")
    print("═══════════════════════════════════════════════════════")

    # ── Step 1: Database ──────────────────────────────────────
    print()
    print("  [1/6] Database Connection")
    print("  ─────────────────────────")
    print("  GrowthClaw needs two database connections:")
    print("  - Customer DB (read-only): your business database to analyze")
    print("  - Internal DB (read-write): where GrowthClaw stores its own data")
    print()

    customer_db = _prompt(
        "Customer database URL",
        env_lines.get("CUSTOMER_DATABASE_URL", ""),
        placeholder="postgresql://user:pass@host:5432/dbname",
    )
    env_lines["CUSTOMER_DATABASE_URL"] = customer_db

    internal_db = _prompt(
        "GrowthClaw internal database URL",
        env_lines.get("GROWTHCLAW_DATABASE_URL", ""),
        placeholder="postgresql://user:pass@host:5432/growthclaw",
    )
    env_lines["GROWTHCLAW_DATABASE_URL"] = internal_db

    # ── Step 2: LLM API Key ──────────────────────────────────
    print()
    print("  [2/6] LLM Provider")
    print("  ──────────────────")
    print("  At least one LLM API key is required.")
    print("  Anthropic Claude is recommended for best results.")
    print()

    anthropic_key = _prompt(
        "Anthropic API key",
        env_lines.get("ANTHROPIC_API_KEY", ""),
        placeholder="sk-ant-...",
        secret=True,
    )
    env_lines["ANTHROPIC_API_KEY"] = anthropic_key

    nvidia_key = _prompt(
        "NVIDIA API key (optional, press Enter to skip)",
        env_lines.get("NVIDIA_API_KEY", ""),
        placeholder="nvapi-...",
        secret=True,
        required=False,
    )
    if nvidia_key:
        env_lines["NVIDIA_API_KEY"] = nvidia_key

    # ── Step 3: Business Context ─────────────────────────────
    print()
    print("  [3/6] Business Context")
    print("  ──────────────────────")
    print("  Helps the LLM understand your data better (optional).")
    print()

    biz_name = _prompt(
        "Business name",
        env_lines.get("GROWTHCLAW_BUSINESS_NAME", ""),
        required=False,
    )
    if biz_name:
        env_lines["GROWTHCLAW_BUSINESS_NAME"] = biz_name

    biz_desc = _prompt(
        "One-line business description",
        env_lines.get("GROWTHCLAW_BUSINESS_DESCRIPTION", ""),
        required=False,
    )
    if biz_desc:
        env_lines["GROWTHCLAW_BUSINESS_DESCRIPTION"] = biz_desc

    # ── Step 4: SMS / Email (optional) ───────────────────────
    print()
    print("  [4/6] Outreach Channels (optional — skip for dry run testing)")
    print("  ──────────────────────────────────────────────────────────────")
    print()

    setup_sms = input("  Set up SMS (Twilio)? [y/N]: ").strip().lower() == "y"
    if setup_sms:
        env_lines["TWILIO_ACCOUNT_SID"] = _prompt("Twilio Account SID", env_lines.get("TWILIO_ACCOUNT_SID", ""))
        env_lines["TWILIO_AUTH_TOKEN"] = _prompt(
            "Twilio Auth Token", env_lines.get("TWILIO_AUTH_TOKEN", ""), secret=True
        )
        env_lines["TWILIO_FROM_NUMBER"] = _prompt("Twilio From Number", env_lines.get("TWILIO_FROM_NUMBER", ""))

    setup_email = input("  Set up Email (Resend)? [y/N]: ").strip().lower() == "y"
    if setup_email:
        env_lines["RESEND_API_KEY"] = _prompt("Resend API key", env_lines.get("RESEND_API_KEY", ""), secret=True)
        env_lines["GROWTHCLAW_FROM_EMAIL"] = _prompt("From email address", env_lines.get("GROWTHCLAW_FROM_EMAIL", ""))

    # ── Step 5: Claude Code + Channels ─────────────────────────
    print()
    print("  [5/7] Claude Code")
    print("  ─────────────────")

    has_claude = shutil.which("claude") is not None
    if has_claude:
        print("  Claude Code CLI detected.")
        print()
        print("  Checking login status...")
        result = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"  Version: {result.stdout.strip()}")
        else:
            print("  Not logged in. Run: claude login")
    else:
        print("  Claude Code CLI not found.")
        print("  Install: npm install -g @anthropic-ai/claude-code")
        print("  Then: claude login")
    print()
    print("  Claude Code is used for the operator agent interface.")
    print("  It's optional — GrowthClaw works standalone without it.")

    # ── Step 6: Operator Channel ──────────────────────────────
    print()
    print("  [6/7] Operator Communication Channel")
    print("  ─────────────────────────────────────")
    print()
    print("  Choose how you'll talk to the GrowthClaw agent:")
    print()
    print("  1. Telegram   — Chat with the agent from your phone")
    print("  2. Discord    — Chat via a Discord bot in your server")
    print("  3. Slack      — Chat via a Slack bot in your workspace")
    print("  4. CLI only   — Use Claude Code terminal (no messaging channel)")
    print("  5. Skip       — Configure later with: growthclaw channels <channel>")
    print()
    ch_choice = input("  Select [1/2/3/4/5] (default: 5): ").strip() or "5"

    if ch_choice == "1":
        from growthclaw.channels import setup_telegram

        setup_telegram()
    elif ch_choice == "2":
        from growthclaw.channels import setup_discord

        setup_discord()
    elif ch_choice == "3":
        _setup_slack()
    elif ch_choice == "4":
        print("  CLI mode selected. Use: growthclaw daemon start --claude")
    else:
        print("  Skipped. Configure later with: growthclaw channels telegram")

    # ── Step 7: Permission Mode ──────────────────────────────
    print()
    print("  [7/7] Agent Permission Mode")
    print("  ───────────────────────────")
    print()
    print("  1. Recommended — Agent never blocks. Dangerous commands denied.")
    print("  2. Strict — GrowthClaw tools only. Other actions need approval.")
    print("  3. Full autonomy — No permission checks (sandboxed only).")
    print()
    perm_choice = input("  Select [1/2/3] (default: 1): ").strip() or "1"

    # ── Write .env ───────────────────────────────────────────
    _write_env(env_path, env_lines)

    # ── Write permissions ────────────────────────────────────
    from growthclaw.channels import setup_permissions

    mode_map = {"1": "recommended", "2": "strict", "3": "full"}
    setup_permissions(mode_map.get(perm_choice, "recommended"))

    # ── Set up MCP + Skill ───────────────────────────────────
    from growthclaw.channels import setup_mcp, setup_skill

    setup_mcp()
    setup_skill()

    # ── Summary ──────────────────────────────────────────────
    print()
    print("═══════════════════════════════════════════════════════")
    print("  Setup Complete!")
    print("═══════════════════════════════════════════════════════")
    print()
    print(f"  Workspace: {workspace}")
    print(f"  Config: {env_path}")
    print(f"  Dry run: {'yes' if env_lines.get('GROWTHCLAW_DRY_RUN', 'true') == 'true' else 'no'}")
    print()
    print("  Next steps:")
    print("    growthclaw migrate          # Create internal tables")
    print("    growthclaw onboard          # Discover your database")
    print("    growthclaw triggers approve  # Review and approve triggers")
    print("    growthclaw daemon start      # Start standalone listener")
    print("    growthclaw daemon start --claude  # Start with Claude Code agent")
    print()


def _setup_slack() -> None:
    """Interactive Slack channel setup."""
    print()
    print("  Slack Channel Setup")
    print("  ───────────────────")
    print()
    print("  1. Go to https://api.slack.com/apps → Create New App")
    print("  2. Choose 'From scratch' → name it 'GrowthClaw'")
    print("  3. Go to OAuth & Permissions → add scopes:")
    print("     - chat:write, channels:history, app_mentions:read")
    print("  4. Install to workspace → copy the Bot Token")
    print()

    token = input("  Paste your Slack Bot Token (xoxb-...): ").strip()
    if not token:
        print("  Skipped.")
        return

    print()
    print("  Run this command to connect Slack:")
    print(f"  claude channel add slack --token {token}")
    print()
    print("  Then mention @GrowthClaw in any channel to talk to the agent.")


def _prompt(label: str, current: str = "", placeholder: str = "", secret: bool = False, required: bool = True) -> str:
    """Prompt for a value, showing current value if set."""
    display_current = "***" if (secret and current) else current
    hint = f" [{display_current}]" if current else (f" ({placeholder})" if placeholder else "")

    while True:
        value = input(f"  {label}{hint}: ").strip()
        if not value and current:
            return current
        if not value and not required:
            return ""
        if not value and required:
            print(f"  {label} is required.")
            continue
        return value


def _write_env(path: Path, values: dict[str, str]) -> None:
    """Write .env file preserving comments from template."""
    # Read existing file to preserve comments and structure
    template = path.read_text() if path.exists() else ""

    # Update values in existing content
    output_lines = []
    written_keys: set[str] = set()

    for line in template.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in values and values[key]:
                output_lines.append(f"{key}={values[key]}")
                written_keys.add(key)
            else:
                output_lines.append(line)
                written_keys.add(key)
        else:
            output_lines.append(line)

    # Append any new keys not in template
    for key, val in values.items():
        if key not in written_keys and val:
            output_lines.append(f"{key}={val}")

    path.write_text("\n".join(output_lines) + "\n")
