"""Pydantic models for schema discovery results."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class ForeignKey(BaseModel):
    column: str
    references_table: str
    references_column: str


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    udt_name: str = ""
    is_nullable: str = "YES"
    column_default: str | None = None
    character_maximum_length: int | None = None
    sample_values: list[str] = Field(default_factory=list)
    null_rate: float | None = None
    distinct_count: int | None = None

    @field_validator("sample_values", mode="before")
    @classmethod
    def coerce_sample_values(cls, v: list) -> list[str]:  # type: ignore[type-arg]
        """Filter out None values and coerce non-strings to str."""
        return [str(x) for x in v if x is not None]


class TableInfo(BaseModel):
    name: str
    row_count: int = 0
    columns: list[ColumnInfo] = Field(default_factory=list)
    primary_keys: list[str] = Field(default_factory=list)
    foreign_keys: list[ForeignKey] = Field(default_factory=list)


class RawSchema(BaseModel):
    tables: list[TableInfo] = Field(default_factory=list)


class ColumnStats(BaseModel):
    name: str
    data_type: str
    null_count: int = 0
    null_rate: float = 0.0
    distinct_count: int = 0
    top_values: list[dict[str, int]] | None = None  # [{"value": count}, ...]
    min_value: str | None = None
    max_value: str | None = None
    avg_value: float | None = None


class TableSample(BaseModel):
    table_name: str
    row_count: int = 0
    columns: list[ColumnStats] = Field(default_factory=list)


class AdditionalProfileTable(BaseModel):
    table: str
    fk_column: str
    useful_columns: list[str] = Field(default_factory=list)
    description: str = ""


class BusinessConcepts(BaseModel):
    """The LLM-mapped business concepts — single source of truth for the entire system."""

    business_type: str = ""
    business_description: str = ""

    # Customer identity
    customer_table: str
    customer_id_column: str
    customer_name_column: str | None = None
    customer_email_column: str | None = None
    customer_phone_column: str | None = None
    customer_created_at_column: str | None = None
    customer_status_column: str | None = None
    customer_timezone_column: str | None = None
    customer_type_column: str | None = None
    customer_type_value: str | None = None
    soft_delete_column: str | None = None
    exclude_filters: list[str] = Field(default_factory=list)

    # Contact consent
    sms_consent_column: str | None = None
    sms_consent_check: str | None = None
    push_token_column: str | None = None

    # Activation
    activation_table: str | None = None
    activation_event: str | None = None
    activation_fk_column: str | None = None
    activation_check_sql: str | None = None
    activation_soft_delete: str | None = None

    # Transactions
    transaction_table: str | None = None
    transaction_fk_column: str | None = None
    transaction_amount_column: str | None = None
    transaction_amount_is_cents: bool = True
    transaction_status_column: str | None = None
    transaction_completed_value: str | None = None
    transaction_date_column: str | None = None

    # Subscriptions
    subscription_table: str | None = None
    subscription_fk_column: str | None = None
    subscription_status_column: str | None = None
    subscription_active_value: str | None = None
    subscription_cancelled_value: str | None = None
    subscription_amount_column: str | None = None
    subscription_frequency_column: str | None = None

    # Attribution
    attribution_table: str | None = None
    attribution_fk_column: str | None = None
    attribution_source_column: str | None = None
    attribution_campaign_column: str | None = None

    # Additional tables useful for profiling
    additional_profile_tables: list[AdditionalProfileTable] = Field(default_factory=list)


class FunnelStage(BaseModel):
    name: str
    table: str
    event: str
    count: int = 0
    description: str = ""


class FunnelDropoff(BaseModel):
    from_stage: str
    to_stage: str
    conversion_rate: float
    lost_customers: int = 0
    description: str = ""


class ActivationWindow(BaseModel):
    optimal_minutes: int = 30
    reasoning: str = ""


class Reachability(BaseModel):
    sms_reachable_in_dropoff: int = 0
    email_reachable_in_dropoff: int = 0
    push_reachable_in_dropoff: int = 0


class Funnel(BaseModel):
    model_config = {"populate_by_name": True}

    stages: list[FunnelStage] = Field(default_factory=list, alias="funnel_stages")
    biggest_dropoff: FunnelDropoff | None = None
    activation_window: ActivationWindow | None = None
    reachability: Reachability | None = None


class RelationshipEdge(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    inferred: bool = False  # True if LLM-inferred rather than explicit FK


class RelationshipGraph(BaseModel):
    edges: list[RelationshipEdge] = Field(default_factory=list)


class SchemaMap(BaseModel):
    """Top-level discovery result persisted to growthclaw.schema_map."""

    id: UUID = Field(default_factory=uuid4)
    version: int = 1
    database_url_hash: str = ""
    business_name: str = ""
    business_type: str = ""
    tables: list[TableInfo] = Field(default_factory=list)
    concepts: BusinessConcepts | None = None
    relationships: RelationshipGraph = Field(default_factory=RelationshipGraph)
    funnel: Funnel = Field(default_factory=Funnel)
    raw_statistics: dict | None = None
    discovered_at: datetime = Field(default_factory=datetime.now)
