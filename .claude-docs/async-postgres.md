# asyncpg Patterns for GrowthClaw

## Connection Pooling

Always use a pool, never raw connections in production code:

```python
import asyncpg

pool = await asyncpg.create_pool(
    dsn=database_url,
    min_size=2,
    max_size=10,
    command_timeout=30,
)

# Always use async with for connection acquisition
async with pool.acquire() as conn:
    rows = await conn.fetch("SELECT * FROM users LIMIT 10")
```

Never hold a connection outside an `async with` block — it won't be returned to the pool.

## Two Pools Pattern

GrowthClaw uses two separate connection pools:
- **Customer pool**: read-only, connects to customer DB
- **Internal pool**: read-write, connects to growthclaw schema

```python
customer_pool = await asyncpg.create_pool(dsn=customer_url, min_size=1, max_size=5)
internal_pool = await asyncpg.create_pool(dsn=growthclaw_url, min_size=2, max_size=10)
```

## Parameterized Queries

asyncpg uses $1, $2, ... for parameters (NOT %s or ?):

```python
row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
rows = await conn.fetch("SELECT * FROM orders WHERE user_id = $1 AND status = $2", user_id, "completed")
```

## LISTEN/NOTIFY for CDC

The CDC listener requires a **dedicated connection** (not from the pool) because LISTEN holds the connection open:

```python
conn = await asyncpg.connect(dsn=database_url)
await conn.add_listener("growthclaw_events", callback)

# callback signature:
def callback(conn, pid, channel, payload):
    data = json.loads(payload)
    # process event
```

Key constraints:
- pg_notify payload max is ~8000 bytes
- LISTEN connection must stay alive — implement reconnection logic
- One LISTEN connection can subscribe to multiple channels

## Dynamic SQL Safety

When building SQL from discovered schema (table names, column names), use `asyncpg.utils.quote_ident()` or format with care:

```python
# Safe: use quote_ident for identifiers
table = "users"  # from discovery
query = f"SELECT * FROM {asyncpg.utils._quote_ident(table)} WHERE id = $1"

# Better: validate identifiers against information_schema before using
```

Never interpolate user-provided values into SQL — always use $N parameters for values.

## Fetching Patterns

```python
# Single row
row = await conn.fetchrow("SELECT ...", arg)  # Returns Record or None
value = await conn.fetchval("SELECT count(*) ...", arg)  # Returns single value

# Multiple rows
rows = await conn.fetch("SELECT ...", arg)  # Returns list[Record]
# Convert to dicts:
data = [dict(r) for r in rows]

# Execute (no return)
await conn.execute("INSERT INTO ...", arg)
```

## Transaction Pattern

```python
async with conn.transaction():
    await conn.execute("INSERT INTO ...", args)
    await conn.execute("UPDATE ...", args)
    # auto-commits on exit, auto-rollbacks on exception
```

## Schema Introspection Queries

Key queries for schema discovery:

```sql
-- Tables with row counts
SELECT t.table_name,
       (SELECT reltuples::bigint FROM pg_class WHERE relname = t.table_name) as approx_rows
FROM information_schema.tables t
WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE';

-- Foreign keys
SELECT tc.table_name, kcu.column_name,
       ccu.table_name AS references_table, ccu.column_name AS references_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu USING (constraint_name, table_schema)
JOIN information_schema.constraint_column_usage ccu USING (constraint_name, table_schema)
WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public';
```

## Error Handling

Common asyncpg exceptions:
- `asyncpg.ConnectionDoesNotExistError` — connection was closed
- `asyncpg.InterfaceError` — connection pool exhausted
- `asyncpg.UndefinedTableError` — table doesn't exist
- `asyncpg.PostgresError` — base class for all PG errors
