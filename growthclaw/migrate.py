"""Run GrowthClaw SQL migrations against the internal database."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import asyncpg

from growthclaw.config import get_settings

logger = logging.getLogger("growthclaw.migrate")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def run_migrations(database_url: str | None = None) -> None:
    """Run all SQL migration files in order against the GrowthClaw internal database."""
    if database_url is None:
        settings = get_settings()
        database_url = settings.growthclaw_database_url

    conn = await asyncpg.connect(dsn=database_url)
    try:
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        for migration_file in migration_files:
            logger.info("Running migration: %s", migration_file.name)
            sql = migration_file.read_text()
            await conn.execute(sql)
            logger.info("Migration complete: %s", migration_file.name)
    finally:
        await conn.close()


def main() -> None:
    """CLI entry point for running migrations."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    asyncio.run(run_migrations())


if __name__ == "__main__":
    main()
