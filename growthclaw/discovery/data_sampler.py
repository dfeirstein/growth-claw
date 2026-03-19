"""Data sampler — samples rows from each table and computes distributions for LLM context."""

from __future__ import annotations

import logging

import asyncpg

from growthclaw.models.schema_map import ColumnInfo, ColumnStats, RawSchema, TableSample

logger = logging.getLogger("growthclaw.discovery.sampler")

# Column types that map to specific sampling strategies
TEXT_TYPES = {"character varying", "text", "varchar", "char", "character", "name"}
NUMERIC_TYPES = {"integer", "bigint", "smallint", "numeric", "decimal", "real", "double precision", "money"}
TIMESTAMP_TYPES = {"timestamp without time zone", "timestamp with time zone", "date", "timestamptz", "timestamp"}
BOOLEAN_TYPES = {"boolean"}


def _classify_column(col: ColumnInfo) -> str:
    """Classify a column by its data type for sampling strategy."""
    dt = col.data_type.lower()
    if dt in TEXT_TYPES:
        return "text"
    if dt in NUMERIC_TYPES:
        return "numeric"
    if dt in TIMESTAMP_TYPES:
        return "timestamp"
    if dt in BOOLEAN_TYPES:
        return "boolean"
    return "other"


async def sample_table(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    table_name: str,
    columns: list[ColumnInfo],
    sample_size: int = 500,
) -> TableSample:
    """Sample a single table and compute per-column statistics."""
    column_stats: list[ColumnStats] = []

    for col in columns:
        try:
            stats = await _sample_column(conn, table_name, col, sample_size)
            column_stats.append(stats)
        except Exception as e:
            logger.warning("Failed to sample %s.%s: %s", table_name, col.name, e)
            column_stats.append(ColumnStats(name=col.name, data_type=col.data_type))

    # Get actual row count
    row_count = await conn.fetchval(f'SELECT COUNT(*) FROM "{table_name}"')  # noqa: S608

    return TableSample(table_name=table_name, row_count=row_count or 0, columns=column_stats)


async def _sample_column(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    table_name: str,
    col: ColumnInfo,
    sample_size: int,
) -> ColumnStats:
    """Compute statistics for a single column."""
    col_type = _classify_column(col)
    name = col.name

    # Base stats: null count, distinct count
    base = await conn.fetchrow(
        f'SELECT COUNT(*) FILTER (WHERE "{name}" IS NULL) as null_count, '  # noqa: S608
        f'COUNT(DISTINCT "{name}") as distinct_count, '
        f"COUNT(*) as total "
        f'FROM (SELECT "{name}" FROM "{table_name}" LIMIT $1) sub',
        sample_size,
    )

    null_count = base["null_count"] if base else 0
    distinct_count = base["distinct_count"] if base else 0
    total = base["total"] if base else 1
    null_rate = null_count / total if total > 0 else 0.0

    stats = ColumnStats(
        name=name,
        data_type=col.data_type,
        null_count=null_count,
        null_rate=round(null_rate, 4),
        distinct_count=distinct_count,
    )

    # Type-specific stats
    if col_type == "text" and distinct_count > 0:
        top = await conn.fetch(
            f'SELECT "{name}"::text as val, COUNT(*) as cnt '  # noqa: S608
            f'FROM (SELECT "{name}" FROM "{table_name}" WHERE "{name}" IS NOT NULL LIMIT $1) sub '
            f'GROUP BY "{name}" ORDER BY cnt DESC LIMIT 10',
            sample_size,
        )
        stats.top_values = [{str(r["val"]): r["cnt"]} for r in top]

    elif col_type == "numeric":
        agg = await conn.fetchrow(
            f'SELECT MIN("{name}")::text as min_val, '  # noqa: S608
            f'MAX("{name}")::text as max_val, '
            f'AVG("{name}")::float as avg_val '
            f'FROM (SELECT "{name}" FROM "{table_name}" WHERE "{name}" IS NOT NULL LIMIT $1) sub',
            sample_size,
        )
        if agg:
            stats.min_value = agg["min_val"]
            stats.max_value = agg["max_val"]
            stats.avg_value = round(agg["avg_val"], 2) if agg["avg_val"] is not None else None

    elif col_type == "timestamp":
        agg = await conn.fetchrow(
            f'SELECT MIN("{name}")::text as min_val, '  # noqa: S608
            f'MAX("{name}")::text as max_val '
            f'FROM (SELECT "{name}" FROM "{table_name}" WHERE "{name}" IS NOT NULL LIMIT $1) sub',
            sample_size,
        )
        if agg:
            stats.min_value = agg["min_val"]
            stats.max_value = agg["max_val"]

    elif col_type == "boolean":
        top = await conn.fetch(
            f'SELECT "{name}"::text as val, COUNT(*) as cnt '  # noqa: S608
            f'FROM (SELECT "{name}" FROM "{table_name}" WHERE "{name}" IS NOT NULL LIMIT $1) sub '
            f'GROUP BY "{name}"',
            sample_size,
        )
        stats.top_values = [{str(r["val"]): r["cnt"]} for r in top]

    return stats


def _get_sample_values(stats: ColumnStats) -> list[str]:
    """Extract sample values from column stats for LLM context."""
    if stats.top_values:
        return [list(v.keys())[0] for v in stats.top_values[:5]]
    values = []
    if stats.min_value:
        values.append(stats.min_value)
    if stats.max_value:
        values.append(stats.max_value)
    return values


async def sample_all(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    raw_schema: RawSchema,
    sample_size: int = 500,
) -> dict[str, TableSample]:
    """Sample all tables with data and return a dict of table_name → TableSample."""
    samples: dict[str, TableSample] = {}
    for table in raw_schema.tables:
        if table.row_count > 0:
            try:
                sample = await sample_table(conn, table.name, table.columns, sample_size)
                samples[table.name] = sample
                logger.info("Sampled %s: %d rows, %d columns", table.name, sample.row_count, len(sample.columns))
            except Exception as e:
                logger.warning("Failed to sample table %s: %s", table.name, e)
    return samples


def enrich_schema_with_samples(raw_schema: RawSchema, samples: dict[str, TableSample]) -> None:
    """Enrich RawSchema columns with sample values and null rates from sampling."""
    for table in raw_schema.tables:
        table_sample = samples.get(table.name)
        if not table_sample:
            continue
        stats_by_name = {s.name: s for s in table_sample.columns}
        for col in table.columns:
            col_stats = stats_by_name.get(col.name)
            if col_stats:
                col.null_rate = col_stats.null_rate
                col.distinct_count = col_stats.distinct_count
                col.sample_values = _get_sample_values(col_stats)
