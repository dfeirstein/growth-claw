"""GrowthClaw main orchestration — onboard, start, and stop the engine."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from growthclaw.config import Settings, get_settings
from growthclaw.discovery import (
    concept_mapper,
    data_sampler,
    funnel_analyzer,
    relationship_resolver,
    schema_scanner,
    schema_store,
)
from growthclaw.experiments import experiment_manager, experiment_store, outcome_checker
from growthclaw.intelligence import profile_analyzer, profile_builder, profile_store
from growthclaw.llm.client import LLMClient, create_llm_client
from growthclaw.models.journey import Journey
from growthclaw.models.schema_map import BusinessConcepts, Funnel
from growthclaw.models.trigger import TriggerEvent, TriggerRule
from growthclaw.outreach import channel_resolver, journey_store, message_composer, sms_sender
from growthclaw.outreach.email_sender import EmailSender
from growthclaw.triggers import cdc_listener, trigger_evaluator, trigger_installer, trigger_proposer, trigger_store
from growthclaw.triggers.frequency_manager import check_global_frequency, record_send

logger = logging.getLogger("growthclaw.main")


class GrowthClaw:
    """Main GrowthClaw engine orchestrating all components."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.llm_client: LLMClient = create_llm_client(
            nvidia_api_key=self.settings.nvidia_api_key,
            anthropic_api_key=self.settings.anthropic_api_key,
            nvidia_nim_url=self.settings.nvidia_nim_url,
            usage_conn_factory=self._get_usage_conn,
        )
        self.sms = sms_sender.SMSSender(self.settings)
        self.email = EmailSender(self.settings)
        self.scheduler = AsyncIOScheduler()
        self.listener: cdc_listener.CDCListener | None = None
        self.customer_pool: asyncpg.Pool | None = None  # type: ignore[type-arg]
        self.internal_pool: asyncpg.Pool | None = None  # type: ignore[type-arg]
        self.concepts: BusinessConcepts | None = None
        self.funnel: Funnel | None = None

    async def _get_usage_conn(self) -> asyncpg.Connection:  # type: ignore[type-arg]
        """Get a connection for LLM usage tracking."""
        await self._ensure_pools()
        assert self.internal_pool
        return await self.internal_pool.acquire()

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

    async def close(self) -> None:
        """Close all resources."""
        if self.listener:
            await self.listener.stop()
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        if self.customer_pool:
            await self.customer_pool.close()
        if self.internal_pool:
            await self.internal_pool.close()

    # -------------------------------------------------------------------------
    # ONBOARDING
    # -------------------------------------------------------------------------

    async def onboard(self) -> None:
        """Run the full discovery + analysis + trigger proposal pipeline."""
        await self._ensure_pools()
        assert self.customer_pool and self.internal_pool

        # Auto-run migrations if schema doesn't exist
        needs_migrate = False
        try:
            check_conn = await asyncpg.connect(dsn=self.settings.growthclaw_database_url)
            try:
                await check_conn.fetchval(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'growthclaw' AND table_name = 'schema_map'"
                )
                result = await check_conn.fetchval(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'growthclaw'"
                )
                if not result or result == 0:
                    needs_migrate = True
            finally:
                await check_conn.close()
        except Exception:
            needs_migrate = True

        if needs_migrate:
            print("Running migrations (first time setup)...")
            from growthclaw.migrate import run_migrations

            await run_migrations(self.settings.growthclaw_database_url)
            print()

        print("\U0001f43e GrowthClaw — Connecting to your database...\n")

        # Step 1: Scan schema
        print("[1/6] Scanning database schema...")
        async with self.customer_pool.acquire() as conn:
            raw_schema = await schema_scanner.scan_schema_with_conn(conn)
        total_cols = sum(len(t.columns) for t in raw_schema.tables)
        print(f"  Found {len(raw_schema.tables)} tables, {total_cols} columns\n")

        # Step 2: Sample data
        print("[2/6] Sampling data distributions...")
        async with self.customer_pool.acquire() as conn:
            samples = await data_sampler.sample_all(conn, raw_schema, self.settings.sample_rows)
        data_sampler.enrich_schema_with_samples(raw_schema, samples)
        print(f"  Sampled {len(samples)} tables with data\n")

        # Step 3: LLM classifies schema
        print("[3/6] Understanding your business...")
        self.concepts = await concept_mapper.map_concepts(
            raw_schema,
            samples,
            self.llm_client,
            business_name=self.settings.business_name,
            business_description=self.settings.business_description,
        )
        print(f"  Business type: {self.concepts.business_type}")
        print(f"  Customer table: {self.concepts.customer_table}")
        print(f"  Activation event: {self.concepts.activation_event}\n")

        # Step 4: Analyze funnel
        print("[4/6] Analyzing customer funnel...")
        async with self.customer_pool.acquire() as conn:
            self.funnel = await funnel_analyzer.analyze_funnel(self.concepts, conn, self.llm_client)
        stages_str = " -> ".join(s.name for s in self.funnel.stages)
        print(f"  Funnel stages: {stages_str}")
        if self.funnel.biggest_dropoff:
            print(f"  Biggest drop-off: {self.funnel.biggest_dropoff.description}\n")

        # Step 5: Resolve relationships + propose triggers
        print("[5/6] Proposing growth triggers...")
        relationships = relationship_resolver.resolve_relationships(raw_schema, self.concepts)
        triggers = await trigger_proposer.propose_triggers(self.concepts, self.funnel, self.llm_client)
        for i, t in enumerate(triggers, 1):
            print(f"  {i}. [{t.channel.upper()}] {t.name}: {t.description}")
            print(f"     Delay: {t.delay_minutes}min | Expected audience: ~{t.expected_audience_per_week}/week")
        print()

        # Step 6: Persist everything
        print("[6/6] Saving configuration...")
        async with self.internal_pool.acquire() as conn:
            await schema_store.save(
                conn,
                raw_schema,
                self.concepts,
                self.funnel,
                relationships,
                database_url=self.settings.customer_database_url,
                business_name=self.settings.business_name,
            )
            await trigger_store.save_all(conn, triggers)

        # Generate BUSINESS.md in workspace
        self._generate_business_md(raw_schema, triggers)

        # Summary
        print("\n\u2705 GrowthClaw discovery complete!\n")
        print(f"  Business: {self.concepts.business_type} — {self.concepts.business_description}")
        if self.funnel.stages:
            print(f"  Customers: {self.funnel.stages[0].count:,}")
        if self.funnel.biggest_dropoff:
            print(f"  Biggest opportunity: {self.funnel.biggest_dropoff.description}")
        print(f"  {len(triggers)} triggers proposed\n")
        print("Next steps:")
        print("  growthclaw triggers approve    # Review and approve proposed triggers")
        print("  growthclaw start               # Install CDC triggers and start listening")
        print("  growthclaw status              # Check system health")

    def _generate_business_md(self, raw_schema: object, triggers: list) -> None:
        """Generate BUSINESS.md in the workspace from discovery results."""
        from growthclaw.workspace import generate_business_md, get_workspace

        if not self.concepts or not self.funnel:
            return

        workspace = get_workspace()
        customer_count = self.funnel.stages[0].count if self.funnel.stages else 0
        activated_count = self.funnel.stages[1].count if len(self.funnel.stages) > 1 else 0
        activation_rate = (activated_count / customer_count * 100) if customer_count > 0 else 0

        content = generate_business_md(
            business_name=self.settings.business_name or self.concepts.business_description,
            business_type=self.concepts.business_type,
            business_description=self.concepts.business_description,
            table_count=len(raw_schema.tables) if hasattr(raw_schema, "tables") else 0,
            customer_table=self.concepts.customer_table,
            customer_count=customer_count,
            customer_id_column=self.concepts.customer_id_column,
            funnel_stages=[s.model_dump() for s in self.funnel.stages],
            biggest_dropoff=self.funnel.biggest_dropoff.model_dump() if self.funnel.biggest_dropoff else None,
            activation_event=self.concepts.activation_event or "unknown",
            activation_table=self.concepts.activation_table or "unknown",
            activation_rate=activation_rate,
            optimal_minutes=self.funnel.activation_window.optimal_minutes if self.funnel.activation_window else 30,
            reachability=self.funnel.reachability.model_dump() if self.funnel.reachability else None,
            key_tables=[t.name for t in raw_schema.tables[:20]] if hasattr(raw_schema, "tables") else [],
            triggers=[
                {
                    "name": t.name,
                    "channel": t.channel,
                    "description": t.description,
                    "delay_minutes": t.delay_minutes,
                    "expected_audience_per_week": t.expected_audience_per_week,
                }
                for t in triggers
            ],
        )

        business_md = workspace / "BUSINESS.md"
        business_md.write_text(content)
        print(f"  Business profile written to: {business_md}")

    # -------------------------------------------------------------------------
    # START / STOP
    # -------------------------------------------------------------------------

    async def start(self) -> None:
        """Install CDC triggers on approved triggers and start the event loop."""
        await self._ensure_pools()
        assert self.customer_pool and self.internal_pool

        # Load concepts if not already loaded
        if not self.concepts:
            async with self.internal_pool.acquire() as conn:
                schema_map = await schema_store.load(conn, self.settings.customer_database_url)
            if not schema_map or not schema_map.concepts:
                print("No discovery data found. Run 'growthclaw onboard' first.")
                return
            self.concepts = schema_map.concepts
            self.funnel = schema_map.funnel

        # Get approved triggers
        async with self.internal_pool.acquire() as conn:
            triggers = await trigger_store.get_active(conn)

        if not triggers:
            print("No approved triggers found. Run 'growthclaw triggers approve' first.")
            return

        # Install CDC triggers
        print(f"Installing {len(triggers)} CDC triggers...")
        async with self.customer_pool.acquire() as cconn:
            async with self.internal_pool.acquire() as iconn:
                for trigger in triggers:
                    name = await trigger_installer.install_trigger(cconn, iconn, trigger, self.concepts)
                    await trigger_store.set_active(iconn, trigger.id)
                    print(f"  Installed: {name}")

        # Start outcome checker (polls every 5 minutes)
        self.scheduler.add_job(
            self._check_outcomes,
            "interval",
            minutes=5,
            id="outcome_checker",
        )
        self.scheduler.start()

        # Start CDC listener
        print("\nListening for events...")
        self.listener = cdc_listener.CDCListener(
            dsn=self.settings.customer_database_url,
            on_event=self._handle_event,
        )
        await self.listener.start()

    async def stop(self) -> None:
        """Stop the listener and uninstall CDC triggers."""
        await self._ensure_pools()
        assert self.customer_pool and self.internal_pool

        if self.listener:
            await self.listener.stop()

        async with self.customer_pool.acquire() as cconn:
            async with self.internal_pool.acquire() as iconn:
                count = await trigger_installer.uninstall_all(cconn, iconn)
        print(f"Stopped. Uninstalled {count} triggers.")

        await self.close()

    # -------------------------------------------------------------------------
    # EVENT PROCESSING PIPELINE
    # -------------------------------------------------------------------------

    async def _handle_event(self, event: TriggerEvent) -> None:
        """Process a single CDC event through the full pipeline."""
        assert self.customer_pool and self.internal_pool and self.concepts

        try:
            # Get the trigger config
            async with self.internal_pool.acquire() as iconn:
                trigger = await trigger_store.get_by_id(iconn, UUID(event.trigger_id))
            if not trigger:
                logger.warning("Unknown trigger_id: %s", event.trigger_id)
                return

            # Log the event
            async with self.internal_pool.acquire() as iconn:
                event_id = await iconn.fetchval(
                    """
                    INSERT INTO growthclaw.events (user_id, table_name, operation, trigger_id, payload)
                    VALUES ($1, $2, $3, $4, $5::jsonb) RETURNING id
                    """,
                    event.user_id,
                    event.table,
                    event.op,
                    trigger.id,
                    f'{{"row_id": "{event.row_id}", "ts": "{event.ts}"}}',
                )

            # Schedule delayed evaluation
            delay = trigger.delay_minutes
            experiment = None
            arm = None

            # Check for active experiments
            async with self.internal_pool.acquire() as iconn:
                experiments = await experiment_store.get_all_active(iconn)
            for exp in experiments:
                if exp.trigger_id == trigger.id:
                    experiment = exp
                    arm = experiment_manager.assign_arm(exp)
                    delay = experiment_manager.get_delay_for_arm(arm)
                    break

            logger.info(
                "Scheduling evaluation in %d minutes for user=%s trigger=%s",
                delay,
                event.user_id,
                trigger.name,
            )

            self.scheduler.add_job(
                self._delayed_evaluate,
                "date",
                run_date=asyncio.get_event_loop().time() + delay * 60,
                args=[event, trigger, event_id, experiment, arm],
                id=f"eval_{event.user_id}_{trigger.id}_{event_id}",
                replace_existing=True,
            )

        except Exception as e:
            logger.error("Failed to handle event: %s", e, exc_info=True)

    async def _delayed_evaluate(
        self,
        event: TriggerEvent,
        trigger: TriggerRule,
        event_id: UUID,
        experiment: object | None,
        arm: object | None,
    ) -> None:
        """Run after the delay: evaluate, build profile, compose message, send."""
        assert self.customer_pool and self.internal_pool and self.concepts

        try:
            # Evaluate: should we fire?
            async with self.customer_pool.acquire() as cconn:
                async with self.internal_pool.acquire() as iconn:
                    should_fire = await trigger_evaluator.evaluate(
                        event,
                        trigger,
                        cconn,
                        iconn,
                        self.concepts,
                        self.settings,
                    )
            if not should_fire:
                return

            # Build customer profile
            async with self.customer_pool.acquire() as cconn:
                profile_data = await profile_builder.build_profile(cconn, event.user_id, trigger)

            # Analyze profile
            brief = await profile_analyzer.analyze_profile(
                profile_data,
                self.concepts,
                trigger.message_context,
                self.llm_client,
                business_name=self.settings.business_name,
            )

            # Cache profile
            async with self.internal_pool.acquire() as iconn:
                await profile_store.save(iconn, event.user_id, profile_data, brief)

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

            # Compose message (SMS or email)
            provider_id = None
            if trigger.channel == "email":
                email_result = await message_composer.compose_email(
                    trigger,
                    profile_data,
                    brief,
                    self.concepts,
                    self.llm_client,
                    cta_link=self.settings.cta_url,
                    business_name=self.settings.business_name,
                )
                message_body = email_result["html_body"]

                journey = Journey(
                    user_id=event.user_id,
                    trigger_id=trigger.id,
                    event_id=event_id,
                    channel="email",
                    contact_info=contact.value,
                    message_body=message_body,
                    experiment_id=experiment.id if hasattr(experiment, "id") else None,
                    experiment_arm=arm.name if hasattr(arm, "name") else None,
                )
                async with self.internal_pool.acquire() as iconn:
                    await journey_store.create(iconn, journey)

                if contact.value:
                    provider_id = await self.email.send(
                        to_email=contact.value,
                        subject=email_result["subject"],
                        html_body=email_result["html_body"],
                        plain_text=email_result.get("plain_text"),
                    )
            else:
                message = await message_composer.compose(
                    trigger,
                    profile_data,
                    brief,
                    self.concepts,
                    self.llm_client,
                    cta_link=self.settings.cta_url,
                    business_name=self.settings.business_name,
                )
                message_body = message

                journey = Journey(
                    user_id=event.user_id,
                    trigger_id=trigger.id,
                    event_id=event_id,
                    channel="sms",
                    contact_info=contact.value,
                    message_body=message_body,
                    experiment_id=experiment.id if hasattr(experiment, "id") else None,
                    experiment_arm=arm.name if hasattr(arm, "name") else None,
                )
                async with self.internal_pool.acquire() as iconn:
                    await journey_store.create(iconn, journey)

                if contact.value:
                    provider_id = await self.sms.send(contact.value, message)

            # Update journey status + record fire + track frequency
            status = "sent" if provider_id or self.settings.dry_run else "failed"
            async with self.internal_pool.acquire() as iconn:
                await journey_store.update_sent(iconn, journey.id, provider_id, status)
                await trigger_evaluator.record_fire(iconn, event.user_id, trigger)
                await record_send(iconn, event.user_id, trigger.channel)

                # Track experiment send
                if hasattr(experiment, "id") and hasattr(arm, "name"):
                    await experiment_store.record_send(iconn, experiment.id, arm.name)

            logger.info(
                "Pipeline complete: user=%s trigger=%s channel=%s status=%s",
                event.user_id,
                trigger.name,
                trigger.channel,
                status,
            )

        except Exception as e:
            logger.error("Pipeline failed for user=%s: %s", event.user_id, e, exc_info=True)

    async def _check_outcomes(self) -> None:
        """Periodic job to check for conversions."""
        assert self.customer_pool and self.internal_pool
        try:
            async with self.customer_pool.acquire() as cconn:
                async with self.internal_pool.acquire() as iconn:
                    resolved = await outcome_checker.check_outcomes(cconn, iconn)
            if resolved > 0:
                logger.info("Resolved %d outcomes", resolved)
        except Exception as e:
            logger.error("Outcome check failed: %s", e)


async def run_onboard() -> None:
    """Convenience function to run onboarding."""
    engine = GrowthClaw()
    try:
        await engine.onboard()
    finally:
        await engine.close()


async def run_start() -> None:
    """Convenience function to start the engine."""
    engine = GrowthClaw()
    try:
        await engine.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await engine.close()
