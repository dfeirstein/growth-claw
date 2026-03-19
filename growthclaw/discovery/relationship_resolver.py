"""Relationship resolver — builds entity relationship graph from explicit FKs and LLM inference."""

from __future__ import annotations

import logging

from growthclaw.models.schema_map import BusinessConcepts, RawSchema, RelationshipEdge, RelationshipGraph

logger = logging.getLogger("growthclaw.discovery.relationships")


def resolve_relationships(raw_schema: RawSchema, concepts: BusinessConcepts) -> RelationshipGraph:
    """Build a relationship graph from explicit foreign keys.

    Inferred relationships from naming conventions are also added
    (e.g., columns named "user_id" pointing to the customer table).
    """
    edges: list[RelationshipEdge] = []
    seen: set[tuple[str, str, str, str]] = set()

    # Step 1: Explicit FK relationships
    for table in raw_schema.tables:
        for fk in table.foreign_keys:
            key = (table.name, fk.column, fk.references_table, fk.references_column)
            if key not in seen:
                seen.add(key)
                edges.append(
                    RelationshipEdge(
                        from_table=table.name,
                        from_column=fk.column,
                        to_table=fk.references_table,
                        to_column=fk.references_column,
                        inferred=False,
                    )
                )

    # Step 2: Inferred relationships from naming conventions
    customer_table = concepts.customer_table
    customer_id = concepts.customer_id_column

    # Common FK naming patterns that point to the customer table
    customer_fk_patterns = [
        f"{customer_id}",  # e.g., "id" if customer table PK is "id"
        "user_id",
        "customer_id",
        "client_id",
        "account_id",
        "member_id",
        "owner_id",
    ]

    for table in raw_schema.tables:
        if table.name == customer_table:
            continue
        for col in table.columns:
            col_name = col.name.lower()
            if col_name in customer_fk_patterns:
                key = (table.name, col.name, customer_table, customer_id)
                if key not in seen:
                    # Check if there's already an explicit FK for this column
                    has_explicit = any(fk.column == col.name for fk in table.foreign_keys)
                    if not has_explicit:
                        seen.add(key)
                        edges.append(
                            RelationshipEdge(
                                from_table=table.name,
                                from_column=col.name,
                                to_table=customer_table,
                                to_column=customer_id,
                                inferred=True,
                            )
                        )

    logger.info(
        "Relationship graph: %d edges (%d explicit, %d inferred)",
        len(edges),
        sum(1 for e in edges if not e.inferred),
        sum(1 for e in edges if e.inferred),
    )

    return RelationshipGraph(edges=edges)
