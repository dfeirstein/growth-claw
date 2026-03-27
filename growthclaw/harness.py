"""GrowthClaw Harness — unified daemon with Python fast loop + Claude Code cron scheduler.

The harness runs two modes together:
1. Python Fast Loop (always running, zero LLM cost):
   - Polling listener detects new events from customer DB
   - Trigger evaluator enforces cooldowns, consent, quiet hours
   - Frequency cap enforcement
   - Approved events queued in growthclaw.event_queue
   - Outcome checker runs every 5 minutes

2. Claude Code Cron (scheduled wake-ups):
   - Every 15 min: Process event queue -> compose messages with VOICE.md -> send
   - Every 6 hours: AutoResearch cycle
   - Daily 2 AM: Nightly sweep
   - Weekly: Self-hosting pass (prompt optimization)

Session Management:
   - On first run, captures the Claude Code session ID
   - Stores it at ~/.growthclaw/session_id
   - All cron wake-ups use --resume <session-id> for context continuity
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import signal
from pathlib import Path
from uuid import UUID

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from growthclaw.config import Settings, get_settings
from growthclaw.outreach import channel_resolver
from growthclaw.triggers import trigger_evaluator, trigger_store
from growthclaw.triggers.frequency_manager import check_global_frequency

logger = logging.getLogger("growthclaw.harness")

GROWTHCLAW_HOME = Path.home() / ".growthclaw"
SESSION_FILE = GROWTHCLAW_HOME / "session_id"
PID_FILE = GROWTHCLAW_HOME / "harness.pid"


class Harness:
    """Unified daemon: Python fast loop + Claude Code cron scheduler."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.scheduler = AsyncIOScheduler()
        self.customer_pool: asyncpg.Pool | None = None  # type: ignore[type-arg]
        self.internal_pool: asyncpg.Pool | None = None  # type: ignore[type-arg]
        self.concepts = None
        self.session_id: str | None = None
        self.listener = None
        self._running = False

    async def _ensure_pools(self) -> None:
        """Create connection pools if they don't exist."""
        if not self.customer_pool:
            self.customer_pool = await asyncpg.create_pool(
                dsn=self.settings.customer_database_url, min_size=1, max_size=5
            )
        if not self.internal_pool:
            self.internal_pool = await asyncpg.create_pool(
                dsn=self.settings.growthclaw_database_url, min_size=2, max_size=10
            )

    async def start(self) -> None:
        """Start the harness: Python fast loop + Claude Code cron."""
        GROWTHCLAW_HOME.mkdir(parents=True, exist_ok=True)
        await self._ensure_pools()
        assert self.customer_pool and self.internal_pool

        # Load concepts from discovery data
        from growthclaw.discovery import schema_store

        async with self.internal_pool.acquire() as conn:
            schema_map = await schema_store.load(conn, self.settings.customer_database_url)
        if not schema_map or not schema_map.concepts:
            logger.error("No discovery data. Run 'growthclaw onboard' first.")
            return
        self.concepts = schema_map.concepts

        # Load or initialize Claude Code session
        self._load_session_id()
        if not self.session_id:
            self.session_id = await self._init_claude_session()
            self._save_session_id()

        # Get active triggers
        async with self.internal_pool.acquire() as conn:
            triggers = await trigger_store.get_active(conn)
        if not triggers:
            logger.error("No approved triggers. Run 'growthclaw triggers approve' first.")
            return

        # Write PID file for daemon management
        PID_FILE.write_text(str(os.getpid()))

        # Start Python fast loop (polling listener)
        self._start_polling(triggers)

        # Schedule Python fast jobs
        self.scheduler.add_job(self._check_outcomes, "interval", minutes=5, id="outcome_checker")

        # Schedule Claude Code cron wake-ups
        self.scheduler.add_job(
            self._wake_claude,
            "interval",
            minutes=15,
            id="claude_process_events",
            args=[
                "Process the event queue. Use gc_get_pending_events to fetch pending events, "
                "then for each event compose a personalized message using the workspace context "
                "(VOICE.md, SOUL.md, BUSINESS.md), then send it via gc_send_message."
            ],
        )
        self.scheduler.add_job(
            self._wake_claude,
            "interval",
            hours=6,
            id="claude_autoresearch",
            args=[
                "Run an AutoResearch cycle. Use gc_experiments to check current status, "
                "then design the next experiment variant based on memory and past results."
            ],
        )
        self.scheduler.add_job(
            self._wake_claude,
            "cron",
            hour=2,
            id="claude_nightly_sweep",
            args=[
                "Run the nightly strategic sweep. Analyze cohort data, detect dormancy patterns, "
                "and store findings in memory via gc_memory_store."
            ],
        )
        self.scheduler.add_job(
            self._wake_claude,
            "cron",
            day_of_week="sun",
            hour=3,
            id="claude_prompt_optimization",
            args=[
                "Run the weekly self-hosting pass. Analyze which message patterns produced "
                "the best outcomes and propose prompt template improvements."
            ],
        )

        self.scheduler.start()
        self._running = True

        logger.info(
            "Harness started: polling=%ss, claude_session=%s",
            self.settings.poll_interval_seconds,
            self.session_id,
        )

        # Keep running until stopped
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    def _start_polling(self, triggers: list) -> None:
        """Start the polling listener for the Python fast loop."""
        from growthclaw.triggers.polling_listener import PollingListener

        self.listener = PollingListener(
            customer_dsn=self.settings.customer_database_url,
            internal_dsn=self.settings.growthclaw_database_url,
            triggers=triggers,
            concepts=self.concepts.model_dump() if self.concepts else {},
            on_event=self._handle_event,
            poll_interval=self.settings.poll_interval_seconds,
        )
        # Start in background task
        asyncio.create_task(self.listener.start())

    async def _handle_event(self, event) -> None:
        """Python fast loop: evaluate event and queue if approved.

        This is the KEY CHANGE from the old architecture. Instead of:
          event -> evaluate -> LLM compose -> send (all in Python)

        Now it's:
          event -> evaluate -> queue (Python) -> Claude Code composes -> send (via MCP)
        """
        assert self.customer_pool and self.internal_pool and self.concepts

        try:
            # Get trigger config
            async with self.internal_pool.acquire() as iconn:
                trigger = await trigger_store.get_by_id(iconn, UUID(event.trigger_id))
            if not trigger:
                logger.warning("Unknown trigger_id: %s", event.trigger_id)
                return

            # Evaluate: cooldowns, consent, quiet hours
            async with self.customer_pool.acquire() as cconn:
                async with self.internal_pool.acquire() as iconn:
                    should_fire = await trigger_evaluator.evaluate(
                        event, trigger, cconn, iconn, self.concepts, self.settings
                    )
            if not should_fire:
                return

            # Resolve contact info
            async with self.customer_pool.acquire() as cconn:
                contact = await channel_resolver.resolve(cconn, event.user_id, self.concepts, trigger.channel)
            if not contact.is_reachable:
                logger.info("User %s not reachable via %s", event.user_id, trigger.channel)
                return

            # Check suppression (unsubscribed, bounced, complained)
            async with self.internal_pool.acquire() as iconn:
                if await channel_resolver.is_suppressed(iconn, event.user_id, trigger.channel):
                    logger.info("User %s is suppressed for %s", event.user_id, trigger.channel)
                    return

            # Check global frequency caps
            max_day = self.settings.max_sms_per_day if trigger.channel == "sms" else self.settings.max_email_per_day
            max_week = self.settings.max_sms_per_week if trigger.channel == "sms" else self.settings.max_email_per_week
            async with self.internal_pool.acquire() as iconn:
                if not await check_global_frequency(iconn, event.user_id, trigger.channel, max_day, max_week):
                    logger.info("User %s hit frequency cap for %s", event.user_id, trigger.channel)
                    return

            # Build profile (Python, no LLM)
            from growthclaw.intelligence import profile_builder

            async with self.customer_pool.acquire() as cconn:
                profile_data = await profile_builder.build_profile(cconn, event.user_id, trigger)

            # Check AutoResearch variant assignment
            ar_cycle_id = None
            ar_arm = None
            async with self.internal_pool.acquire() as iconn:
                running_cycle = await iconn.fetchrow(
                    "SELECT id FROM growthclaw.autoresearch_cycles "
                    "WHERE trigger_id = $1 AND status = 'running' LIMIT 1",
                    trigger.id,
                )
            if running_cycle:
                hash_input = f"{event.user_id}:{running_cycle['id']}"
                hash_val = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)  # noqa: S324
                ar_arm = "test" if hash_val % 2 == 1 else "control"
                ar_cycle_id = running_cycle["id"]

            # Log the event
            async with self.internal_pool.acquire() as iconn:
                event_id = await iconn.fetchval(
                    """INSERT INTO growthclaw.events (user_id, table_name, operation, trigger_id, payload)
                    VALUES ($1, $2, $3, $4, $5::jsonb) RETURNING id""",
                    event.user_id,
                    event.table,
                    event.op,
                    trigger.id,
                    json.dumps({"row_id": event.row_id, "ts": event.ts}),
                )

            # QUEUE for Claude Code composition (instead of composing in Python)
            # Column names match growthclaw.event_queue from migration 006
            async with self.internal_pool.acquire() as iconn:
                await iconn.execute(
                    """INSERT INTO growthclaw.event_queue
                    (user_id, trigger_id, event_id, channel, contact_value,
                     profile_data, intelligence, ar_cycle_id, ar_arm)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb, '{}'::jsonb, $7, $8)""",
                    event.user_id,
                    trigger.id,
                    event_id,
                    trigger.channel,
                    contact.value,
                    json.dumps(profile_data),
                    ar_cycle_id,
                    ar_arm,
                )

            # Record the trigger fire (frequency send recorded later at actual send time
            # by gc_send_message MCP tool — recording here would double-count)
            async with self.internal_pool.acquire() as iconn:
                await trigger_evaluator.record_fire(iconn, event.user_id, trigger)

            logger.info("Event queued: user=%s trigger=%s channel=%s", event.user_id, trigger.name, trigger.channel)

        except Exception as e:
            logger.error("Failed to handle event: %s", e, exc_info=True)

    async def _wake_claude(self, prompt: str) -> None:
        """Wake up Claude Code with a prompt via --resume."""
        if not self.session_id:
            logger.warning("No Claude Code session ID. Skipping wake-up.")
            return

        if not shutil.which("claude"):
            logger.warning("Claude Code CLI not found. Skipping wake-up.")
            return

        cmd = [
            "claude",
            "--resume",
            self.session_id,
            "--auto-mode",
            "-p",
            prompt,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(GROWTHCLAW_HOME),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

            if proc.returncode == 0:
                logger.info("Claude Code wake-up complete (prompt: %s...)", prompt[:50])
            else:
                logger.error("Claude Code wake-up failed: %s", stderr.decode()[:200])
        except TimeoutError:
            logger.error("Claude Code wake-up timed out (5 min)")
        except Exception as e:
            logger.error("Claude Code wake-up error: %s", e)

    async def _init_claude_session(self) -> str | None:
        """Initialize a new Claude Code session and capture the session ID."""
        if not shutil.which("claude"):
            logger.warning("Claude Code CLI not found. Running in standalone mode.")
            return None

        cmd = [
            "claude",
            "--auto-mode",
            "-p",
            (
                "You are the GrowthClaw AI marketing agent. Read your workspace files "
                "(CLAUDE.md, SOUL.md, VOICE.md, BUSINESS.md) to understand your role. "
                "Confirm you're ready by saying 'GrowthClaw agent initialized.'"
            ),
            "--output-format",
            "json",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(GROWTHCLAW_HOME),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            # Parse session_id from JSON output (may have trailing non-JSON lines)
            stdout_text = stdout.decode().strip() if stdout else ""
            stderr_text = stderr.decode().strip() if stderr else ""

            if proc.returncode != 0:
                logger.error("Claude Code init failed (rc=%d): %s", proc.returncode, stderr_text[:200])
                return None

            # Find the JSON line in stdout (skip non-JSON lines like "Shell cwd was reset")
            for line in stdout_text.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        result = json.loads(line)
                        session_id = result.get("session_id")
                        if session_id:
                            logger.info("Claude Code session initialized: %s", session_id)
                            return session_id
                    except json.JSONDecodeError:
                        continue

            logger.warning(
                "Could not capture session ID from Claude Code. stdout=%s", stdout_text[:200]
            )
            return None
        except TimeoutError:
            logger.error("Claude Code session init timed out (2 min)")
            return None
        except Exception as e:
            logger.error("Failed to init Claude Code session: %s", e)
            return None

    def _load_session_id(self) -> None:
        """Load session ID from persistent storage."""
        if SESSION_FILE.exists():
            sid = SESSION_FILE.read_text().strip()
            if sid:
                self.session_id = sid
                logger.info("Loaded session ID: %s", self.session_id)

    def _save_session_id(self) -> None:
        """Save session ID to persistent storage."""
        if self.session_id:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            SESSION_FILE.write_text(self.session_id)

    async def _check_outcomes(self) -> None:
        """Periodic Python job: check for conversion outcomes."""
        assert self.customer_pool and self.internal_pool
        try:
            from growthclaw.experiments import outcome_checker

            async with self.customer_pool.acquire() as cconn:
                async with self.internal_pool.acquire() as iconn:
                    resolved = await outcome_checker.check_outcomes(cconn, iconn)
            if resolved > 0:
                logger.info("Resolved %d outcomes", resolved)
        except Exception as e:
            logger.error("Outcome check failed: %s", e)

    async def stop(self) -> None:
        """Stop the harness gracefully."""
        self._running = False
        if self.listener is not None:
            try:
                await self.listener.stop()
            except Exception as e:
                logger.error("Error stopping listener: %s", e)
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        if self.customer_pool:
            await self.customer_pool.close()
        if self.internal_pool:
            await self.internal_pool.close()
        PID_FILE.unlink(missing_ok=True)
        logger.info("Harness stopped.")


async def run_harness() -> None:
    """Entry point for running the harness."""
    harness = Harness()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(harness.stop()))

    await harness.start()
