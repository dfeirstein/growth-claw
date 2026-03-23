"""GrowthClaw CLI — command-line interface for all operations."""

from __future__ import annotations

import asyncio
import json
import logging

import click

from growthclaw.config import get_settings


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def main(verbose: bool) -> None:
    """GrowthClaw — AI marketing engine that learns any business."""
    _setup_logging(verbose)


@main.command()
def init() -> None:
    """Initialize GrowthClaw workspace at ~/.growthclaw/."""
    from growthclaw.workspace import get_workspace, init_workspace, is_initialized

    if is_initialized():
        print(f"  Workspace already exists at {get_workspace()}")
        rerun = click.confirm("  Re-run setup wizard?", default=False)
        if not rerun:
            return
        from growthclaw.setup_wizard import run_wizard

        run_wizard(get_workspace())
        return

    print()
    print("  Creating GrowthClaw workspace at ~/.growthclaw/")
    print()

    business = click.prompt("  Business name (optional)", default="", show_default=False)
    workspace = init_workspace(business_name=business)

    print()
    print(f"  Workspace created at: {workspace}")
    print()

    run_setup = click.confirm("  Run setup wizard now?", default=True)
    if run_setup:
        from growthclaw.setup_wizard import run_wizard

        run_wizard(workspace)
    else:
        print()
        print("  Next steps:")
        print("    growthclaw setup            # Interactive setup wizard")
        print("    growthclaw migrate")
        print("    growthclaw onboard")
        print("    growthclaw daemon start     # Start the agent")


@main.command()
def onboard() -> None:
    """Run full discovery + analysis + trigger proposal."""
    from growthclaw.main import run_onboard

    asyncio.run(run_onboard())


@main.command()
def discover() -> None:
    """Re-run schema discovery only."""
    from growthclaw.main import GrowthClaw

    async def _discover() -> None:
        engine = GrowthClaw()
        try:
            await engine.onboard()
        finally:
            await engine.close()

    asyncio.run(_discover())


@main.group()
def triggers() -> None:
    """Manage trigger rules."""
    pass


@triggers.command(name="list")
def triggers_list() -> None:
    """Show all proposed/active triggers."""
    import asyncpg

    from growthclaw.triggers import trigger_store

    async def _list() -> None:
        settings = get_settings()
        conn = await asyncpg.connect(dsn=settings.growthclaw_database_url)
        try:
            all_triggers = await trigger_store.get_all(conn)
            if not all_triggers:
                print("No triggers found. Run 'growthclaw onboard' first.")
                return
            for t in all_triggers:
                status_icon = {"proposed": "?", "approved": "+", "active": "*", "paused": "-"}.get(t.status, " ")
                print(f"  [{status_icon}] {t.name} ({t.status})")
                print(f"      {t.description}")
                print(
                    f"      Watch: {t.watch_table} {t.watch_event} | Delay: {t.delay_minutes}min | Channel: {t.channel}"
                )
                print()
        finally:
            await conn.close()

    asyncio.run(_list())


@triggers.command(name="approve")
@click.option("--all", "approve_all_flag", is_flag=True, help="Approve all proposed triggers")
def triggers_approve(approve_all_flag: bool) -> None:
    """Approve proposed triggers."""
    import asyncpg

    from growthclaw.triggers import trigger_store

    async def _approve() -> None:
        settings = get_settings()
        conn = await asyncpg.connect(dsn=settings.growthclaw_database_url)
        try:
            if approve_all_flag:
                count = await trigger_store.approve_all(conn)
                print(f"Approved {count} triggers.")
            else:
                all_triggers = await trigger_store.get_all(conn)
                proposed = [t for t in all_triggers if t.status == "proposed"]
                if not proposed:
                    print("No proposed triggers to approve.")
                    return
                for t in proposed:
                    print(f"\n  {t.name}: {t.description}")
                    print(f"  Watch: {t.watch_table} {t.watch_event} | Delay: {t.delay_minutes}min")
                    answer = input("  Approve? [y/N] ").strip().lower()
                    if answer == "y":
                        await trigger_store.approve(conn, t.id)
                        print(f"  Approved: {t.name}")
        finally:
            await conn.close()

    asyncio.run(_approve())


@main.command()
def start() -> None:
    """Install CDC triggers and start the event loop."""
    from growthclaw.main import run_start

    asyncio.run(run_start())


@main.command()
def stop() -> None:
    """Stop listening and remove CDC triggers."""
    from growthclaw.main import GrowthClaw

    async def _stop() -> None:
        engine = GrowthClaw()
        try:
            await engine.stop()
        finally:
            await engine.close()

    asyncio.run(_stop())


@main.command()
def status() -> None:
    """Health check: DB connection, active triggers, recent events."""
    import asyncpg

    async def _status() -> None:
        settings = get_settings()

        # Check customer DB
        try:
            conn = await asyncpg.connect(dsn=settings.customer_database_url)
            table_count = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables"
                " WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
            await conn.close()
            print(f"  Customer DB: connected ({table_count} tables)")
        except Exception as e:
            print(f"  Customer DB: FAILED ({e})")

        # Check internal DB
        try:
            conn = await asyncpg.connect(dsn=settings.growthclaw_database_url)

            trigger_count = await conn.fetchval("SELECT COUNT(*) FROM growthclaw.triggers WHERE status = 'active'")
            event_count = await conn.fetchval("SELECT COUNT(*) FROM growthclaw.events WHERE processed = FALSE")
            journey_count = await conn.fetchval("SELECT COUNT(*) FROM growthclaw.journeys")

            print("  Internal DB: connected")
            print(f"  Active triggers: {trigger_count}")
            print(f"  Unprocessed events: {event_count}")
            print(f"  Total journeys: {journey_count}")
            print(f"  Dry run: {settings.dry_run}")
            await conn.close()
        except Exception as e:
            print(f"  Internal DB: FAILED ({e})")

    asyncio.run(_status())


@main.command()
@click.option("-n", "--limit", default=20, help="Number of journeys to show")
def journeys(limit: int) -> None:
    """Show recent outreach with outcomes."""
    import asyncpg

    from growthclaw.outreach import journey_store

    async def _journeys() -> None:
        settings = get_settings()
        conn = await asyncpg.connect(dsn=settings.growthclaw_database_url)
        try:
            recent = await journey_store.get_recent(conn, limit=limit)
            if not recent:
                print("No journeys found.")
                return
            for j in recent:
                outcome_str = j.outcome or "pending"
                print(f"  [{j.status}] user={j.user_id} channel={j.channel} outcome={outcome_str}")
                print(f"    Message: {j.message_body[:80]}{'...' if len(j.message_body) > 80 else ''}")
                print(f"    Sent: {j.sent_at or 'not sent'}")
                print()
        finally:
            await conn.close()

    asyncio.run(_journeys())


@main.command()
def experiments() -> None:
    """Show experiment results."""
    import asyncpg

    from growthclaw.experiments import experiment_store

    async def _experiments() -> None:
        settings = get_settings()
        conn = await asyncpg.connect(dsn=settings.growthclaw_database_url)
        try:
            active = await experiment_store.get_all_active(conn)
            if not active:
                print("No active experiments.")
                return
            for exp in active:
                print(f"\n  Experiment: {exp.name}")
                print(f"  Variable: {exp.variable} | Metric: {exp.metric}")
                results = await experiment_store.get_results(conn, exp.id)
                for r in results:
                    rate = f"{r.conversion_rate:.1%}"
                    print(f"    Arm '{r.arm_name}': {r.total_sent} sent, {r.total_converted} converted ({rate})")
        finally:
            await conn.close()

    asyncio.run(_experiments())


@main.command(name="export")
def export_data() -> None:
    """Export schema_map, triggers, and results as JSON."""
    import asyncpg

    from growthclaw.discovery import schema_store
    from growthclaw.triggers import trigger_store

    async def _export() -> None:
        settings = get_settings()
        conn = await asyncpg.connect(dsn=settings.growthclaw_database_url)
        try:
            schema_map = await schema_store.load(conn, settings.customer_database_url)
            all_triggers = await trigger_store.get_all(conn)

            data = {
                "schema_map": schema_map.model_dump(mode="json") if schema_map else None,
                "triggers": [t.model_dump(mode="json") for t in all_triggers],
            }
            print(json.dumps(data, indent=2, default=str))
        finally:
            await conn.close()

    asyncio.run(_export())


@main.command()
def migrate() -> None:
    """Run database migrations."""
    from growthclaw.migrate import main as run_migrate

    run_migrate()


@main.command()
def dashboard() -> None:
    """Open the GrowthClaw dashboard."""
    import subprocess

    subprocess.Popen(  # noqa: S603, S607
        ["streamlit", "run", "growthclaw/dashboard/app.py", "--server.port", "8501"],
    )
    click.echo("Dashboard running at http://localhost:8501")


# ─── Daemon Commands ───────────────────────────────────────────────────────


@main.group()
def daemon() -> None:
    """Manage the GrowthClaw agent daemon."""
    pass


@daemon.command(name="start")
@click.option("--claude", "use_claude", is_flag=True, help="Run Claude Code CLI in tmux (with channels, MCP, skills)")
@click.option("--no-resume", is_flag=True, help="Start fresh Claude session (don't resume)")
def daemon_start(use_claude: bool, no_resume: bool) -> None:
    """Start the GrowthClaw daemon."""
    from growthclaw.daemon import start

    mode = "claude" if use_claude else "standalone"
    start(mode=mode, resume=not no_resume)


@daemon.command(name="stop")
def daemon_stop() -> None:
    """Stop the GrowthClaw daemon."""
    from growthclaw.daemon import stop

    stop()


@daemon.command(name="status")
def daemon_status() -> None:
    """Show daemon status."""
    from growthclaw.daemon import status

    status()


# ─── Channel Commands ──────────────────────────────────────────────────────


@main.group()
def channels() -> None:
    """Configure operator communication channels."""
    pass


@channels.command(name="telegram")
def channels_telegram() -> None:
    """Set up Telegram as an operator channel."""
    from growthclaw.channels import setup_telegram

    setup_telegram()


@channels.command(name="discord")
def channels_discord() -> None:
    """Set up Discord as an operator channel."""
    from growthclaw.channels import setup_discord

    setup_discord()


@channels.command(name="slack")
def channels_slack() -> None:
    """Set up Slack as an operator channel."""
    from growthclaw.setup_wizard import _setup_slack

    _setup_slack()


@channels.command(name="mcp")
def channels_mcp() -> None:
    """Register GrowthClaw MCP server for Claude Code."""
    from growthclaw.channels import setup_mcp

    setup_mcp()


# ─── Setup Wizard ──────────────────────────────────────────────────────────


@main.command()
def setup() -> None:
    """Interactive setup wizard: database, API keys, channels, permissions."""
    from growthclaw.setup_wizard import run_wizard
    from growthclaw.workspace import get_workspace, is_initialized

    if not is_initialized():
        print("GrowthClaw not initialized. Run: growthclaw init")
        return
    run_wizard(get_workspace())


if __name__ == "__main__":
    main()
