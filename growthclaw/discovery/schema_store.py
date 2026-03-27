"""Schema store — persists discovery results to growthclaw.schema_map."""

from __future__ import annotations

import hashlib
import json
import logging
from uuid import UUID

import asyncpg

from growthclaw.models.schema_map import BusinessConcepts, Funnel, RawSchema, RelationshipGraph, SchemaMap

logger = logging.getLogger("growthclaw.discovery.schema_store")


def _hash_url(url: str) -> str:
    """SHA256 hash of the database URL for identity without storing cleartext."""
    return hashlib.sha256(url.encode()).hexdigest()


async def save(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    raw_schema: RawSchema,
    concepts: BusinessConcepts,
    funnel: Funnel,
    relationships: RelationshipGraph,
    database_url: str,
    business_name: str = "",
    raw_statistics: dict | None = None,
) -> UUID:
    """Persist discovery results to growthclaw.schema_map. Upserts by database_url_hash."""
    url_hash = _hash_url(database_url)

    tables_json = json.dumps([t.model_dump(mode="json") for t in raw_schema.tables])
    concepts_json = json.dumps(concepts.model_dump(mode="json"))
    relationships_json = json.dumps(relationships.model_dump(mode="json"))
    funnel_json = json.dumps(funnel.model_dump(mode="json"))
    stats_json = json.dumps(raw_statistics) if raw_statistics else None

    # Check for existing record
    existing = await conn.fetchrow(
        "SELECT id, version FROM growthclaw.schema_map WHERE database_url_hash = $1",
        url_hash,
    )

    if existing:
        # Update existing record with incremented version
        new_version = existing["version"] + 1
        await conn.execute(
            """
            UPDATE growthclaw.schema_map
            SET version = $1, business_name = $2, business_type = $3,
                tables = $4::jsonb, concepts = $5::jsonb,
                relationships = $6::jsonb, funnel = $7::jsonb,
                raw_statistics = $8::jsonb, discovered_at = NOW()
            WHERE database_url_hash = $9
            """,
            new_version,
            business_name,
            concepts.business_type,
            tables_json,
            concepts_json,
            relationships_json,
            funnel_json,
            stats_json,
            url_hash,
        )
        record_id = existing["id"]
        logger.info("Updated schema_map record %s (version %d)", record_id, new_version)
    else:
        # Insert new record
        record_id = await conn.fetchval(
            """
            INSERT INTO growthclaw.schema_map
                (database_url_hash, business_name, business_type, tables, concepts,
                 relationships, funnel, raw_statistics)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb)
            RETURNING id
            """,
            url_hash,
            business_name,
            concepts.business_type,
            tables_json,
            concepts_json,
            relationships_json,
            funnel_json,
            stats_json,
        )
        logger.info("Created schema_map record %s", record_id)

    return record_id


async def load(conn: asyncpg.Connection, database_url: str) -> SchemaMap | None:  # type: ignore[type-arg]
    """Load the most recent schema map for a given database URL."""
    url_hash = _hash_url(database_url)
    row = await conn.fetchrow(
        "SELECT * FROM growthclaw.schema_map WHERE database_url_hash = $1 ORDER BY version DESC LIMIT 1",
        url_hash,
    )
    if not row:
        return None

    import json

    def _parse_json(val: object) -> dict | list | None:
        """Parse a JSONB value — asyncpg may return str or dict depending on codec."""
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return val
        if isinstance(val, str):
            return json.loads(val)
        return val  # type: ignore[return-value]

    concepts_data = _parse_json(row["concepts"])
    relationships_data = _parse_json(row["relationships"])
    funnel_data = _parse_json(row["funnel"])

    return SchemaMap(
        id=row["id"],
        version=row["version"],
        database_url_hash=row["database_url_hash"],
        business_name=row["business_name"] or "",
        business_type=row["business_type"] or "",
        tables=row["tables"],
        concepts=BusinessConcepts.model_validate(concepts_data) if concepts_data else None,
        relationships=RelationshipGraph.model_validate(relationships_data)
        if relationships_data
        else RelationshipGraph(),
        funnel=Funnel.model_validate(funnel_data) if funnel_data else Funnel(),
        raw_statistics=row["raw_statistics"],
    )
