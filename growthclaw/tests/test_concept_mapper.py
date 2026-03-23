"""Tests for the concept mapper module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from growthclaw.discovery.concept_mapper import map_concepts
from growthclaw.llm.client import LLMClient
from growthclaw.models.schema_map import BusinessConcepts, RawSchema

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_raw_schema(fixture_name: str) -> RawSchema:
    """Load a fixture JSON and parse it into a RawSchema."""
    with open(FIXTURES_DIR / fixture_name) as f:
        data = json.load(f)
    return RawSchema.model_validate(data)


def _make_mock_llm(response_dict: dict) -> LLMClient:
    """Create a mock LLMClient that returns the given dict from call_json."""
    provider = AsyncMock()
    client = LLMClient(provider=provider, provider_name="test")
    client.call_json = AsyncMock(return_value=response_dict)
    return client


# ---------------------------------------------------------------------------
# Ecommerce concept mapping
# ---------------------------------------------------------------------------

ECOMMERCE_LLM_RESPONSE = {
    "business_type": "ecommerce",
    "business_description": "Online retail store selling consumer products",
    "customer_table": "customers",
    "customer_id_column": "id",
    "customer_name_column": "first_name",
    "customer_email_column": "email",
    "customer_phone_column": "phone",
    "customer_created_at_column": "created_at",
    "customer_status_column": "status",
    "customer_type_column": None,
    "customer_type_value": None,
    "soft_delete_column": "deleted_at",
    "exclude_filters": [],
    "sms_consent_column": "sms_opt_in",
    "sms_consent_check": "sms_opt_in = true",
    "activation_table": "orders",
    "activation_event": "first_order_placed",
    "activation_fk_column": "customer_id",
    "activation_check_sql": "SELECT NOT EXISTS(SELECT 1 FROM orders WHERE customer_id = $1)",
    "transaction_table": "orders",
    "transaction_fk_column": "customer_id",
    "transaction_amount_column": "total_cents",
    "transaction_amount_is_cents": True,
    "transaction_status_column": "status",
    "transaction_completed_value": "delivered",
    "transaction_date_column": "created_at",
    "subscription_table": None,
    "subscription_fk_column": None,
    "subscription_status_column": None,
    "subscription_active_value": None,
    "attribution_table": None,
    "attribution_fk_column": None,
    "attribution_source_column": None,
    "attribution_campaign_column": None,
    "additional_profile_tables": [
        {
            "table": "order_items",
            "fk_column": "order_id",
            "useful_columns": ["product_id", "quantity", "unit_price_cents"],
            "description": "Line items for orders, useful for product preferences",
        }
    ],
}


async def test_ecommerce_concept_mapping():
    """Ecommerce fixture maps to correct business concepts."""
    schema = _load_raw_schema("ecommerce_schema.json")
    llm = _make_mock_llm(ECOMMERCE_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm, business_name="TestShop")
    assert isinstance(result, BusinessConcepts)
    assert result.business_type == "ecommerce"
    assert result.customer_table == "customers"
    assert result.customer_id_column == "id"


async def test_ecommerce_activation_concept():
    """Ecommerce activation is first order placed."""
    schema = _load_raw_schema("ecommerce_schema.json")
    llm = _make_mock_llm(ECOMMERCE_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm)
    assert result.activation_table == "orders"
    assert result.activation_event == "first_order_placed"
    assert result.activation_fk_column == "customer_id"


async def test_ecommerce_transaction_concept():
    """Ecommerce transaction table is orders with status/amount."""
    schema = _load_raw_schema("ecommerce_schema.json")
    llm = _make_mock_llm(ECOMMERCE_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm)
    assert result.transaction_table == "orders"
    assert result.transaction_amount_column == "total_cents"
    assert result.transaction_amount_is_cents is True
    assert result.transaction_completed_value == "delivered"


async def test_ecommerce_sms_consent():
    """Ecommerce SMS consent is via the sms_opt_in column."""
    schema = _load_raw_schema("ecommerce_schema.json")
    llm = _make_mock_llm(ECOMMERCE_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm)
    assert result.sms_consent_column == "sms_opt_in"
    assert result.sms_consent_check == "sms_opt_in = true"


async def test_ecommerce_no_subscription():
    """Ecommerce does not have subscriptions."""
    schema = _load_raw_schema("ecommerce_schema.json")
    llm = _make_mock_llm(ECOMMERCE_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm)
    assert result.subscription_table is None


async def test_ecommerce_soft_delete():
    """Ecommerce uses deleted_at for soft deletes."""
    schema = _load_raw_schema("ecommerce_schema.json")
    llm = _make_mock_llm(ECOMMERCE_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm)
    assert result.soft_delete_column == "deleted_at"


async def test_ecommerce_additional_profile_tables():
    """Order items is recognized as additional profile data."""
    schema = _load_raw_schema("ecommerce_schema.json")
    llm = _make_mock_llm(ECOMMERCE_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm)
    assert len(result.additional_profile_tables) == 1
    assert result.additional_profile_tables[0].table == "order_items"


# ---------------------------------------------------------------------------
# SaaS concept mapping
# ---------------------------------------------------------------------------

SAAS_LLM_RESPONSE = {
    "business_type": "saas",
    "business_description": "B2B SaaS platform with team-based subscriptions",
    "customer_table": "users",
    "customer_id_column": "id",
    "customer_name_column": "full_name",
    "customer_email_column": "email",
    "customer_phone_column": "phone",
    "customer_created_at_column": "created_at",
    "customer_status_column": None,
    "customer_type_column": "role",
    "customer_type_value": None,
    "soft_delete_column": "deleted_at",
    "exclude_filters": [],
    "sms_consent_column": "sms_consent",
    "sms_consent_check": "sms_consent = true",
    "activation_table": "feature_usage",
    "activation_event": "first_feature_used",
    "activation_fk_column": "user_id",
    "activation_check_sql": "SELECT NOT EXISTS(SELECT 1 FROM feature_usage WHERE user_id = $1)",
    "transaction_table": "invoices",
    "transaction_fk_column": "organization_id",
    "transaction_amount_column": "amount_cents",
    "transaction_amount_is_cents": True,
    "transaction_status_column": "status",
    "transaction_completed_value": "paid",
    "transaction_date_column": "created_at",
    "subscription_table": "subscriptions",
    "subscription_fk_column": "organization_id",
    "subscription_status_column": "status",
    "subscription_active_value": "active",
    "subscription_cancelled_value": "cancelled",
    "subscription_amount_column": "amount_cents",
    "subscription_frequency_column": "billing_interval",
    "attribution_table": None,
    "attribution_fk_column": None,
    "attribution_source_column": None,
    "attribution_campaign_column": None,
    "additional_profile_tables": [
        {
            "table": "organizations",
            "fk_column": "id",
            "useful_columns": ["name", "plan", "industry"],
            "description": "Organization the user belongs to",
        },
        {
            "table": "feature_usage",
            "fk_column": "user_id",
            "useful_columns": ["feature_name", "action", "created_at"],
            "description": "Feature usage activity log",
        },
    ],
}


async def test_saas_concept_mapping():
    """SaaS fixture maps to correct top-level concepts."""
    schema = _load_raw_schema("saas_schema.json")
    llm = _make_mock_llm(SAAS_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm, business_name="SaaSApp")
    assert result.business_type == "saas"
    assert result.customer_table == "users"
    assert result.customer_id_column == "id"


async def test_saas_subscription_concept():
    """SaaS correctly identifies subscriptions table."""
    schema = _load_raw_schema("saas_schema.json")
    llm = _make_mock_llm(SAAS_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm)
    assert result.subscription_table == "subscriptions"
    assert result.subscription_status_column == "status"
    assert result.subscription_active_value == "active"
    assert result.subscription_cancelled_value == "cancelled"


async def test_saas_activation_is_feature_usage():
    """SaaS activation event is first feature usage."""
    schema = _load_raw_schema("saas_schema.json")
    llm = _make_mock_llm(SAAS_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm)
    assert result.activation_table == "feature_usage"
    assert result.activation_fk_column == "user_id"


async def test_saas_transaction_is_invoices():
    """SaaS transactions are invoices."""
    schema = _load_raw_schema("saas_schema.json")
    llm = _make_mock_llm(SAAS_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm)
    assert result.transaction_table == "invoices"
    assert result.transaction_completed_value == "paid"


# ---------------------------------------------------------------------------
# Driver service concept mapping
# ---------------------------------------------------------------------------

DRIVER_SERVICE_LLM_RESPONSE = {
    "business_type": "driver_service",
    "business_description": "Premium personal driver service with subscription plans",
    "customer_table": "users",
    "customer_id_column": "id",
    "customer_name_column": "first_name",
    "customer_email_column": "email",
    "customer_phone_column": "phone",
    "customer_created_at_column": "created_at",
    "customer_status_column": "status",
    "customer_timezone_column": "timezone",
    "customer_type_column": "role",
    "customer_type_value": "member",
    "soft_delete_column": "deleted_at",
    "exclude_filters": ["role != 'driver'"],
    "sms_consent_column": "sms_opt_in",
    "sms_consent_check": "sms_opt_in = true",
    "activation_table": "bookings",
    "activation_event": "first_booking_completed",
    "activation_fk_column": "user_id",
    "activation_check_sql": "SELECT NOT EXISTS(SELECT 1 FROM bookings WHERE user_id = $1 AND status = 'completed')",
    "transaction_table": "bookings",
    "transaction_fk_column": "user_id",
    "transaction_amount_column": "total_cents",
    "transaction_amount_is_cents": True,
    "transaction_status_column": "status",
    "transaction_completed_value": "completed",
    "transaction_date_column": "created_at",
    "subscription_table": "subscriptions",
    "subscription_fk_column": "user_id",
    "subscription_status_column": "status",
    "subscription_active_value": "active",
    "subscription_cancelled_value": "cancelled",
    "subscription_amount_column": "monthly_amount_cents",
    "subscription_frequency_column": None,
    "attribution_table": "utms",
    "attribution_fk_column": "user_id",
    "attribution_source_column": "utm_source",
    "attribution_campaign_column": "utm_campaign",
    "additional_profile_tables": [
        {
            "table": "cards",
            "fk_column": "user_id",
            "useful_columns": ["brand", "last_four", "is_default"],
            "description": "Payment cards on file",
        },
        {
            "table": "utms",
            "fk_column": "user_id",
            "useful_columns": ["utm_source", "utm_campaign", "landing_page"],
            "description": "Marketing attribution data",
        },
    ],
}


async def test_driver_service_concept_mapping():
    """Driver service maps to correct concepts."""
    schema = _load_raw_schema("driver_service_schema.json")
    llm = _make_mock_llm(DRIVER_SERVICE_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm, business_name="TestBiz")
    assert result.business_type == "driver_service"
    assert result.customer_table == "users"
    assert result.customer_type_value == "member"


async def test_driver_service_excludes_drivers():
    """Driver service filters out driver role from customers."""
    schema = _load_raw_schema("driver_service_schema.json")
    llm = _make_mock_llm(DRIVER_SERVICE_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm)
    assert "role != 'driver'" in result.exclude_filters


async def test_driver_service_activation_is_booking():
    """Driver service activation is first completed booking."""
    schema = _load_raw_schema("driver_service_schema.json")
    llm = _make_mock_llm(DRIVER_SERVICE_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm)
    assert result.activation_table == "bookings"
    assert result.activation_event == "first_booking_completed"


async def test_driver_service_attribution():
    """Driver service has UTM attribution table."""
    schema = _load_raw_schema("driver_service_schema.json")
    llm = _make_mock_llm(DRIVER_SERVICE_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm)
    assert result.attribution_table == "utms"
    assert result.attribution_source_column == "utm_source"
    assert result.attribution_campaign_column == "utm_campaign"


async def test_driver_service_subscription():
    """Driver service has subscription plans."""
    schema = _load_raw_schema("driver_service_schema.json")
    llm = _make_mock_llm(DRIVER_SERVICE_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm)
    assert result.subscription_table == "subscriptions"
    assert result.subscription_active_value == "active"
    assert result.subscription_amount_column == "monthly_amount_cents"


async def test_driver_service_timezone_column():
    """Driver service user table has timezone for quiet-hours awareness."""
    schema = _load_raw_schema("driver_service_schema.json")
    llm = _make_mock_llm(DRIVER_SERVICE_LLM_RESPONSE)

    result = await map_concepts(schema, {}, llm)
    assert result.customer_timezone_column == "timezone"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_llm_prompt_includes_table_count():
    """The LLM is called with a prompt containing all tables."""
    schema = _load_raw_schema("ecommerce_schema.json")
    llm = _make_mock_llm(ECOMMERCE_LLM_RESPONSE)

    with patch("growthclaw.discovery.concept_mapper.render_template", return_value="mock prompt") as mock_render:
        await map_concepts(schema, {}, llm, business_name="TestShop", business_description="A shop")
        mock_render.assert_called_once()
        call_kwargs = mock_render.call_args
        assert call_kwargs.kwargs["business_name"] == "TestShop"
        assert call_kwargs.kwargs["business_description"] == "A shop"
        assert len(call_kwargs.kwargs["tables"]) == 5


async def test_concept_mapper_passes_low_temperature():
    """Concept mapper uses low temperature for deterministic classification."""
    schema = _load_raw_schema("saas_schema.json")
    llm = _make_mock_llm(SAAS_LLM_RESPONSE)

    await map_concepts(schema, {}, llm)
    llm.call_json.assert_awaited_once()
    call_kwargs = llm.call_json.call_args
    assert call_kwargs.kwargs.get("temperature", call_kwargs.args[1] if len(call_kwargs.args) > 1 else None) == 0.1
