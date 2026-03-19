"""Schema scanner — introspects a PostgreSQL database to extract tables, columns, types, FKs, and row counts."""

from __future__ import annotations

import logging

import asyncpg

from growthclaw.models.schema_map import ColumnInfo, ForeignKey, RawSchema, TableInfo

logger = logging.getLogger("growthclaw.discovery.scanner")


async def scan_schema(db_url: str) -> RawSchema:
    """Connect to a PostgreSQL database and extract the complete schema."""
    conn = await asyncpg.connect(dsn=db_url)
    try:
        return await _scan_with_connection(conn)
    finally:
        await conn.close()


async def scan_schema_with_conn(conn: asyncpg.Connection) -> RawSchema:
    """Scan schema using an existing connection."""
    return await _scan_with_connection(conn)


async def _scan_with_connection(conn: asyncpg.Connection) -> RawSchema:  # type: ignore[type-arg]
    """Internal: run all introspection queries."""
    # Query 1: Tables with approximate row counts
    table_rows = await conn.fetch("""
        SELECT t.table_name,
               COALESCE(
                   (SELECT reltuples::bigint FROM pg_class WHERE relname = t.table_name),
                   0
               ) as approx_rows
        FROM information_schema.tables t
        WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name
    """)

    # Query 2: Columns per table
    column_rows = await conn.fetch("""
        SELECT table_name, column_name, data_type, udt_name,
               is_nullable, column_default, character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    """)

    # Query 3: Foreign keys
    fk_rows = await conn.fetch("""
        SELECT
            tc.table_name, kcu.column_name,
            ccu.table_name AS references_table,
            ccu.column_name AS references_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            USING (constraint_name, table_schema)
        JOIN information_schema.constraint_column_usage ccu
            USING (constraint_name, table_schema)
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
    """)

    # Query 4: Primary keys
    pk_rows = await conn.fetch("""
        SELECT kcu.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            USING (constraint_name, table_schema)
        WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'
    """)

    # Build lookup dicts
    columns_by_table: dict[str, list[ColumnInfo]] = {}
    for row in column_rows:
        table = row["table_name"]
        col = ColumnInfo(
            name=row["column_name"],
            data_type=row["data_type"],
            udt_name=row["udt_name"] or "",
            is_nullable=row["is_nullable"],
            column_default=row["column_default"],
            character_maximum_length=row["character_maximum_length"],
        )
        columns_by_table.setdefault(table, []).append(col)

    fks_by_table: dict[str, list[ForeignKey]] = {}
    for row in fk_rows:
        table = row["table_name"]
        fk = ForeignKey(
            column=row["column_name"],
            references_table=row["references_table"],
            references_column=row["references_column"],
        )
        fks_by_table.setdefault(table, []).append(fk)

    pks_by_table: dict[str, list[str]] = {}
    for row in pk_rows:
        pks_by_table.setdefault(row["table_name"], []).append(row["column_name"])

    # Assemble TableInfo objects
    tables = []
    for row in table_rows:
        name = row["table_name"]
        table = TableInfo(
            name=name,
            row_count=max(0, row["approx_rows"] or 0),
            columns=columns_by_table.get(name, []),
            primary_keys=pks_by_table.get(name, []),
            foreign_keys=fks_by_table.get(name, []),
        )
        tables.append(table)

    logger.info("Schema scan complete: %d tables, %d total columns", len(tables), sum(len(t.columns) for t in tables))
    return RawSchema(tables=tables)
