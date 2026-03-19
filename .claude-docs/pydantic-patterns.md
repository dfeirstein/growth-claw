# Pydantic v2 Patterns for GrowthClaw

## Model Basics (v2 API)

```python
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

class TableInfo(BaseModel):
    name: str
    row_count: int = 0
    columns: list["ColumnInfo"] = Field(default_factory=list)

    # v2: use model_validate, NOT parse_obj
    # v2: use model_dump, NOT .dict()
    # v2: use model_dump_json, NOT .json()
```

## Pydantic Settings for Config

```python
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    customer_database_url: str
    growthclaw_database_url: str
    nvidia_api_key: str | None = None
    anthropic_api_key: str | None = None
    dry_run: bool = True

    model_config = {"env_prefix": "GROWTHCLAW_", "env_file": ".env"}
```

Note: `env_prefix` only applies to fields without explicit `alias`. For fields like
`CUSTOMER_DATABASE_URL` that don't have the prefix, use `alias`:

```python
customer_database_url: str = Field(alias="CUSTOMER_DATABASE_URL")
```

Or use `model_config = {"env_prefix": ""}` and name fields to match env vars exactly.

## JSONB Serialization

For storing Pydantic models in PostgreSQL JSONB columns:

```python
import json

# Model → JSONB (for INSERT/UPDATE)
json_str = model.model_dump_json()
# or for dict:
json_dict = model.model_dump(mode="json")  # ensures all types are JSON-serializable

# JSONB → Model (from SELECT)
model = MyModel.model_validate(json_data)  # json_data is already a dict from asyncpg
```

asyncpg automatically deserializes JSONB columns to Python dicts, so no need to json.loads().

## Optional Fields Pattern

Use `X | None = None` for nullable fields (NOT `Optional[X]`):

```python
class BusinessConcepts(BaseModel):
    customer_table: str
    customer_id_column: str
    customer_email_column: str | None = None
    customer_phone_column: str | None = None
    subscription_table: str | None = None
```

## Enum-like Status Fields

Use Literal types for status fields:

```python
from typing import Literal

class Journey(BaseModel):
    status: Literal["composed", "approved", "sent", "delivered", "failed"] = "composed"
    outcome: Literal["converted", "ignored", "unsubscribed"] | None = None
```

## Nested Models

```python
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

class Funnel(BaseModel):
    stages: list[FunnelStage]
    biggest_dropoff: FunnelDropoff
```

## UUID Fields

```python
from uuid import UUID, uuid4

class TriggerRule(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
```

## Validators

```python
from pydantic import field_validator

class Settings(BaseSettings):
    quiet_hours_start: int = 21
    quiet_hours_end: int = 8

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def validate_hour(cls, v: int) -> int:
        if not 0 <= v <= 23:
            raise ValueError("Hour must be 0-23")
        return v
```

## Model Config Options

```python
class MyModel(BaseModel):
    model_config = {
        "from_attributes": True,     # allow from ORM/Record objects
        "populate_by_name": True,    # allow both alias and field name
        "json_schema_extra": {...},  # extend JSON schema
    }
```
