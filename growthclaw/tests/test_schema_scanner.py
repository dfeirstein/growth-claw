"""Tests for the schema scanner module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from growthclaw.discovery.schema_scanner import scan_schema, scan_schema_with_conn
from growthclaw.models.schema_map import RawSchema

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_record(mapping: dict) -> MagicMock:
    """Create a mock asyncpg Record that supports dict-style access."""
    rec = MagicMock()
    rec.__getitem__ = lambda self, key: mapping[key]
    rec.keys.return_value = mapping.keys()
    rec.values.return_value = mapping.values()
    rec.items.return_value = mapping.items()
    return rec


def _build_mock_conn_from_fixture(fixture_path: str) -> AsyncMock:
    """Build a mock asyncpg connection that returns data matching a fixture file."""
    with open(fixture_path) as f:
        schema = json.load(f)

    table_rows = []
    column_rows = []
    fk_rows = []
    pk_rows = []

    for table in schema["tables"]:
        table_rows.append(
            _make_record(
                {
                    "table_name": table["name"],
                    "approx_rows": table["row_count"],
                }
            )
        )

        for col in table["columns"]:
            column_rows.append(
                _make_record(
                    {
                        "table_name": table["name"],
                        "column_name": col["name"],
                        "data_type": col["data_type"],
                        "udt_name": col["udt_name"],
                        "is_nullable": col["is_nullable"],
                        "column_default": col["column_default"],
                        "character_maximum_length": col["character_maximum_length"],
                    }
                )
            )

        for pk in table["primary_keys"]:
            pk_rows.append(
                _make_record(
                    {
                        "table_name": table["name"],
                        "column_name": pk,
                    }
                )
            )

        for fk in table["foreign_keys"]:
            fk_rows.append(
                _make_record(
                    {
                        "table_name": table["name"],
                        "column_name": fk["column"],
                        "references_table": fk["references_table"],
                        "references_column": fk["references_column"],
                    }
                )
            )

    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=[table_rows, column_rows, fk_rows, pk_rows])
    return conn


# ---------------------------------------------------------------------------
# Tests using the ecommerce fixture
# ---------------------------------------------------------------------------


async def test_scan_ecommerce_returns_raw_schema():
    """Scanning an ecommerce DB returns all tables."""
    conn = _build_mock_conn_from_fixture(FIXTURES_DIR / "ecommerce_schema.json")
    result = await scan_schema_with_conn(conn)
    assert isinstance(result, RawSchema)
    assert len(result.tables) == 5
    table_names = {t.name for t in result.tables}
    assert table_names == {"customers", "products", "checkouts", "orders", "order_items"}


async def test_scan_ecommerce_row_counts():
    """Row counts from the fixture are propagated correctly."""
    conn = _build_mock_conn_from_fixture(FIXTURES_DIR / "ecommerce_schema.json")
    result = await scan_schema_with_conn(conn)
    customers = next(t for t in result.tables if t.name == "customers")
    assert customers.row_count == 45200
    orders = next(t for t in result.tables if t.name == "orders")
    assert orders.row_count == 41800


async def test_scan_ecommerce_columns():
    """Columns are correctly extracted for each table."""
    conn = _build_mock_conn_from_fixture(FIXTURES_DIR / "ecommerce_schema.json")
    result = await scan_schema_with_conn(conn)
    customers = next(t for t in result.tables if t.name == "customers")
    col_names = [c.name for c in customers.columns]
    assert "id" in col_names
    assert "email" in col_names
    assert "sms_opt_in" in col_names
    assert "deleted_at" in col_names


async def test_scan_ecommerce_foreign_keys():
    """Foreign keys are correctly mapped."""
    conn = _build_mock_conn_from_fixture(FIXTURES_DIR / "ecommerce_schema.json")
    result = await scan_schema_with_conn(conn)
    orders = next(t for t in result.tables if t.name == "orders")
    fk_columns = {fk.column for fk in orders.foreign_keys}
    assert "customer_id" in fk_columns
    assert "checkout_id" in fk_columns
    # Verify FK references
    cust_fk = next(fk for fk in orders.foreign_keys if fk.column == "customer_id")
    assert cust_fk.references_table == "customers"
    assert cust_fk.references_column == "id"


async def test_scan_ecommerce_primary_keys():
    """Primary keys are captured."""
    conn = _build_mock_conn_from_fixture(FIXTURES_DIR / "ecommerce_schema.json")
    result = await scan_schema_with_conn(conn)
    for table in result.tables:
        assert "id" in table.primary_keys


async def test_scan_ecommerce_column_types():
    """Column data types are correctly recorded."""
    conn = _build_mock_conn_from_fixture(FIXTURES_DIR / "ecommerce_schema.json")
    result = await scan_schema_with_conn(conn)
    customers = next(t for t in result.tables if t.name == "customers")
    email_col = next(c for c in customers.columns if c.name == "email")
    assert email_col.data_type == "character varying"
    assert email_col.is_nullable == "NO"
    sms_col = next(c for c in customers.columns if c.name == "sms_opt_in")
    assert sms_col.data_type == "boolean"


# ---------------------------------------------------------------------------
# Tests using the SaaS fixture
# ---------------------------------------------------------------------------


async def test_scan_saas_returns_all_tables():
    """SaaS schema fixture contains all expected tables."""
    conn = _build_mock_conn_from_fixture(FIXTURES_DIR / "saas_schema.json")
    result = await scan_schema_with_conn(conn)
    assert len(result.tables) == 5
    table_names = {t.name for t in result.tables}
    assert table_names == {"users", "organizations", "subscriptions", "invoices", "feature_usage"}


async def test_scan_saas_foreign_keys():
    """SaaS foreign keys chain correctly: invoices -> subscriptions -> organizations."""
    conn = _build_mock_conn_from_fixture(FIXTURES_DIR / "saas_schema.json")
    result = await scan_schema_with_conn(conn)
    invoices = next(t for t in result.tables if t.name == "invoices")
    fk_refs = {fk.references_table for fk in invoices.foreign_keys}
    assert "subscriptions" in fk_refs
    assert "organizations" in fk_refs


async def test_scan_saas_uuid_types():
    """SaaS tables use UUID primary keys."""
    conn = _build_mock_conn_from_fixture(FIXTURES_DIR / "saas_schema.json")
    result = await scan_schema_with_conn(conn)
    users = next(t for t in result.tables if t.name == "users")
    id_col = next(c for c in users.columns if c.name == "id")
    assert id_col.data_type == "uuid"


# ---------------------------------------------------------------------------
# Tests using the driver service fixture
# ---------------------------------------------------------------------------


async def test_scan_driver_service_tables():
    """Driver service schema has all tables."""
    conn = _build_mock_conn_from_fixture(FIXTURES_DIR / "driver_service_schema.json")
    result = await scan_schema_with_conn(conn)
    assert len(result.tables) == 5
    table_names = {t.name for t in result.tables}
    assert table_names == {"users", "cards", "bookings", "subscriptions", "utms"}


async def test_scan_driver_service_bookings_fks():
    """Bookings table references users for both user_id and driver_id."""
    conn = _build_mock_conn_from_fixture(FIXTURES_DIR / "driver_service_schema.json")
    result = await scan_schema_with_conn(conn)
    bookings = next(t for t in result.tables if t.name == "bookings")
    fk_cols = {fk.column for fk in bookings.foreign_keys}
    assert "user_id" in fk_cols
    assert "driver_id" in fk_cols
    for fk in bookings.foreign_keys:
        assert fk.references_table == "users"


# ---------------------------------------------------------------------------
# scan_schema (with dsn) test
# ---------------------------------------------------------------------------


async def test_scan_schema_opens_and_closes_connection(monkeypatch):
    """scan_schema creates a connection from DSN and closes it after."""
    mock_conn = _build_mock_conn_from_fixture(FIXTURES_DIR / "ecommerce_schema.json")

    async def mock_connect(dsn):
        return mock_conn

    monkeypatch.setattr("growthclaw.discovery.schema_scanner.asyncpg.connect", mock_connect)

    result = await scan_schema("postgresql://fake:5432/test")
    assert isinstance(result, RawSchema)
    mock_conn.close.assert_awaited_once()


async def test_scan_schema_closes_on_error(monkeypatch):
    """Connection is closed even if scanning raises."""
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(side_effect=RuntimeError("query fail"))

    async def mock_connect(dsn):
        return mock_conn

    monkeypatch.setattr("growthclaw.discovery.schema_scanner.asyncpg.connect", mock_connect)

    with pytest.raises(RuntimeError, match="query fail"):
        await scan_schema("postgresql://fake:5432/test")

    mock_conn.close.assert_awaited_once()


async def test_scan_empty_schema():
    """An empty database returns an empty RawSchema."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=[[], [], [], []])
    result = await scan_schema_with_conn(conn)
    assert isinstance(result, RawSchema)
    assert len(result.tables) == 0
