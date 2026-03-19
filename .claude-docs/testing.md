# Testing Patterns for GrowthClaw

## pytest-asyncio Setup

In `pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["growthclaw/tests"]
```

With `asyncio_mode = "auto"`, all async test functions are automatically detected — no need for `@pytest.mark.asyncio` decorator.

## Async Test Functions

```python
async def test_scan_schema(mock_conn):
    result = await schema_scanner.scan_schema(mock_conn)
    assert len(result.tables) == 5
```

## Mock LLM Responses

Create a fixture that returns predictable JSON for each prompt type:

```python
import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def mock_llm():
    client = AsyncMock()

    async def mock_call(prompt: str, **kwargs) -> str:
        if "classify each table" in prompt.lower():
            return json.dumps(MOCK_CONCEPTS)
        if "customer lifecycle funnel" in prompt.lower():
            return json.dumps(MOCK_FUNNEL)
        if "propose trigger rules" in prompt.lower():
            return json.dumps(MOCK_TRIGGERS)
        return "{}"

    client.call = mock_call
    client.call_json = AsyncMock(side_effect=lambda p, **kw: json.loads(mock_call(p)))
    return client
```

## Mock Database Connections

```python
@pytest.fixture
def mock_conn():
    conn = AsyncMock()

    async def mock_fetch(query, *args):
        if "information_schema.tables" in query:
            return [{"table_name": "users", "approx_rows": 1000}, ...]
        if "information_schema.columns" in query:
            return [...]
        return []

    conn.fetch = AsyncMock(side_effect=mock_fetch)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    conn.execute = AsyncMock()
    return conn
```

## Schema Fixtures

Three fixture files in `tests/fixtures/` to prove genericity:

### ecommerce_schema.json
```json
{
  "tables": [
    {"name": "customers", "row_count": 50000, "columns": [...]},
    {"name": "orders", "row_count": 120000, "columns": [...]},
    {"name": "order_items", "row_count": 350000, "columns": [...]},
    {"name": "products", "row_count": 500, "columns": [...]},
    {"name": "checkouts", "row_count": 200000, "columns": [...]}
  ]
}
```

### saas_schema.json
```json
{
  "tables": [
    {"name": "users", "row_count": 10000, "columns": [...]},
    {"name": "organizations", "row_count": 2000, "columns": [...]},
    {"name": "subscriptions", "row_count": 8000, "columns": [...]},
    {"name": "invoices", "row_count": 45000, "columns": [...]},
    {"name": "feature_usage", "row_count": 500000, "columns": [...]}
  ]
}
```

### driver_service_schema.json
```json
{
  "tables": [
    {"name": "users", "row_count": 6000, "columns": [...]},
    {"name": "cards", "row_count": 800, "columns": [...]},
    {"name": "bookings", "row_count": 15000, "columns": [...]},
    {"name": "subscriptions", "row_count": 500, "columns": [...]},
    {"name": "utms", "row_count": 6000, "columns": [...]}
  ]
}
```

## Testing Trigger Evaluator

Key scenarios to test:
1. Cooldown not exceeded → allow
2. Cooldown exceeded → block
3. SMS consent present → allow
4. SMS consent missing → block
5. Within quiet hours → block
6. Outside quiet hours → allow
7. Max fires reached → block
8. User already activated → block

```python
async def test_cooldown_blocks(mock_conn):
    # Set up: last fired 2 hours ago, cooldown is 24 hours
    mock_conn.fetchrow.return_value = {"fire_count": 1, "last_fired_at": now - timedelta(hours=2)}
    result = await evaluator.evaluate(event, trigger, mock_conn, settings)
    assert result is False

async def test_quiet_hours_blocks(mock_conn, settings):
    settings.quiet_hours_start = 21
    settings.quiet_hours_end = 8
    # Simulate 11 PM
    with freeze_time("2026-01-15 23:00:00"):
        result = await evaluator.evaluate(event, trigger, mock_conn, settings)
        assert result is False
```

## Testing Message Composer

Verify SMS length constraint:

```python
async def test_sms_under_160_chars(mock_llm):
    message = await composer.compose(trigger, profile, concepts, mock_llm)
    assert len(message) <= 160
```
