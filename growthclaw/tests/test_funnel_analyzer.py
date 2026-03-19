"""Tests for the funnel analyzer module — verifies funnel stage computation with mock data."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from growthclaw.discovery.funnel_analyzer import (
    _count_activated,
    _count_customers,
    _count_sms_consent,
    _count_subscribed,
    _count_transacted,
    _time_to_activation_distribution,
    analyze_funnel,
)
from growthclaw.llm.client import LLMClient
from growthclaw.models.schema_map import BusinessConcepts, Funnel


def _make_ecommerce_concepts() -> BusinessConcepts:
    """Create BusinessConcepts for an ecommerce business."""
    return BusinessConcepts(
        business_type="ecommerce",
        business_description="Online retail store",
        customer_table="customers",
        customer_id_column="id",
        customer_created_at_column="created_at",
        soft_delete_column="deleted_at",
        sms_consent_check="sms_opt_in = true",
        activation_table="orders",
        activation_event="first_order_placed",
        activation_fk_column="customer_id",
        transaction_table="orders",
        transaction_fk_column="customer_id",
        transaction_status_column="status",
        transaction_completed_value="delivered",
        transaction_amount_column="total_cents",
    )


def _make_saas_concepts() -> BusinessConcepts:
    """Create BusinessConcepts for a SaaS business."""
    return BusinessConcepts(
        business_type="saas",
        business_description="B2B SaaS with subscriptions",
        customer_table="users",
        customer_id_column="id",
        customer_created_at_column="created_at",
        soft_delete_column="deleted_at",
        sms_consent_check="sms_consent = true",
        activation_table="feature_usage",
        activation_event="first_feature_used",
        activation_fk_column="user_id",
        transaction_table="invoices",
        transaction_fk_column="organization_id",
        transaction_status_column="status",
        transaction_completed_value="paid",
        subscription_table="subscriptions",
        subscription_fk_column="organization_id",
        subscription_status_column="status",
        subscription_active_value="active",
    )


def _make_driver_concepts() -> BusinessConcepts:
    """Create BusinessConcepts for a driver service."""
    return BusinessConcepts(
        business_type="driver_service",
        business_description="Premium personal driver service",
        customer_table="users",
        customer_id_column="id",
        customer_created_at_column="created_at",
        customer_type_column="role",
        customer_type_value="member",
        soft_delete_column="deleted_at",
        sms_consent_check="sms_opt_in = true",
        activation_table="bookings",
        activation_event="first_booking_completed",
        activation_fk_column="user_id",
        transaction_table="bookings",
        transaction_fk_column="user_id",
        transaction_status_column="status",
        transaction_completed_value="completed",
        subscription_table="subscriptions",
        subscription_fk_column="user_id",
        subscription_status_column="status",
        subscription_active_value="active",
    )


# ---------------------------------------------------------------------------
# _count_customers tests
# ---------------------------------------------------------------------------


async def test_count_customers_basic():
    """Counts customers from a simple table."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=45200)
    concepts = _make_ecommerce_concepts()
    count = await _count_customers(conn, concepts)
    assert count == 45200


async def test_count_customers_with_soft_delete_filter():
    """Soft delete filter is applied to customer count query."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=44000)
    concepts = _make_ecommerce_concepts()
    await _count_customers(conn, concepts)
    query_arg = conn.fetchval.call_args[0][0]
    assert '"deleted_at" IS NULL' in query_arg


async def test_count_customers_with_type_filter():
    """Customer type filter is applied for driver service."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=15000)
    concepts = _make_driver_concepts()
    await _count_customers(conn, concepts)
    query_arg = conn.fetchval.call_args[0][0]
    assert '"role"' in query_arg
    assert "'member'" in query_arg


async def test_count_customers_returns_zero_on_null():
    """Returns 0 when fetchval returns None."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=None)
    concepts = _make_ecommerce_concepts()
    count = await _count_customers(conn, concepts)
    assert count == 0


async def test_count_customers_with_exclude_filters():
    """Exclude filters are appended to the WHERE clause."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=14000)
    concepts = _make_driver_concepts()
    concepts.exclude_filters = ["role != 'driver'"]
    await _count_customers(conn, concepts)
    query_arg = conn.fetchval.call_args[0][0]
    assert "role != 'driver'" in query_arg


# ---------------------------------------------------------------------------
# _count_activated tests
# ---------------------------------------------------------------------------


async def test_count_activated():
    """Counts activated customers."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=28000)
    concepts = _make_ecommerce_concepts()
    count = await _count_activated(conn, concepts)
    assert count == 28000


async def test_count_activated_no_table():
    """Returns 0 when no activation table is configured."""
    conn = AsyncMock()
    concepts = _make_ecommerce_concepts()
    concepts.activation_table = None
    count = await _count_activated(conn, concepts)
    assert count == 0


async def test_count_activated_no_fk():
    """Returns 0 when no activation FK column is configured."""
    conn = AsyncMock()
    concepts = _make_ecommerce_concepts()
    concepts.activation_fk_column = None
    count = await _count_activated(conn, concepts)
    assert count == 0


async def test_count_activated_with_soft_delete():
    """Activation soft delete filter is applied."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=25000)
    concepts = _make_ecommerce_concepts()
    concepts.activation_soft_delete = "deleted_at IS NULL"
    await _count_activated(conn, concepts)
    query_arg = conn.fetchval.call_args[0][0]
    assert "deleted_at IS NULL" in query_arg


# ---------------------------------------------------------------------------
# _count_transacted tests
# ---------------------------------------------------------------------------


async def test_count_transacted():
    """Counts transacted customers with status filter."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=20000)
    concepts = _make_ecommerce_concepts()
    count = await _count_transacted(conn, concepts)
    assert count == 20000
    query_arg = conn.fetchval.call_args[0][0]
    assert "'delivered'" in query_arg


async def test_count_transacted_no_table():
    """Returns 0 when no transaction table configured."""
    conn = AsyncMock()
    concepts = _make_ecommerce_concepts()
    concepts.transaction_table = None
    count = await _count_transacted(conn, concepts)
    assert count == 0


async def test_count_transacted_no_status_filter():
    """Counts without status filter when not configured."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=30000)
    concepts = _make_ecommerce_concepts()
    concepts.transaction_status_column = None
    concepts.transaction_completed_value = None
    count = await _count_transacted(conn, concepts)
    assert count == 30000


# ---------------------------------------------------------------------------
# _count_subscribed tests
# ---------------------------------------------------------------------------


async def test_count_subscribed_saas():
    """Counts subscribed organizations in SaaS."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=3200)
    concepts = _make_saas_concepts()
    count = await _count_subscribed(conn, concepts)
    assert count == 3200
    query_arg = conn.fetchval.call_args[0][0]
    assert "'active'" in query_arg


async def test_count_subscribed_driver():
    """Counts subscribed users in driver service."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=4500)
    concepts = _make_driver_concepts()
    count = await _count_subscribed(conn, concepts)
    assert count == 4500


async def test_count_subscribed_no_table():
    """Returns 0 when no subscription table exists."""
    conn = AsyncMock()
    concepts = _make_ecommerce_concepts()
    count = await _count_subscribed(conn, concepts)
    assert count == 0


# ---------------------------------------------------------------------------
# _count_sms_consent tests
# ---------------------------------------------------------------------------


async def test_count_sms_consent():
    """Counts customers with SMS consent."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=18000)
    concepts = _make_ecommerce_concepts()
    count = await _count_sms_consent(conn, concepts)
    assert count == 18000


async def test_count_sms_consent_no_check():
    """Returns 0 when no SMS consent check is configured."""
    conn = AsyncMock()
    concepts = _make_ecommerce_concepts()
    concepts.sms_consent_check = None
    count = await _count_sms_consent(conn, concepts)
    assert count == 0


# ---------------------------------------------------------------------------
# _time_to_activation_distribution tests
# ---------------------------------------------------------------------------


async def test_time_to_activation_distribution():
    """Time distribution is computed when activation info is present."""
    mock_row = {
        "within_15min": 5000,
        "within_30min": 8000,
        "within_1hour": 12000,
        "within_24hours": 22000,
        "total": 28000,
        "median_minutes": 42.5,
    }
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=mock_row)
    concepts = _make_ecommerce_concepts()
    dist = await _time_to_activation_distribution(conn, concepts)
    assert dist["within_15min"] == 5000
    assert dist["median_minutes"] == 42.5
    assert dist["total_activated"] == 28000


async def test_time_to_activation_no_activation_table():
    """Returns empty dict when no activation table."""
    conn = AsyncMock()
    concepts = _make_ecommerce_concepts()
    concepts.activation_table = None
    dist = await _time_to_activation_distribution(conn, concepts)
    assert dist == {}


async def test_time_to_activation_no_created_at():
    """Returns empty dict when no customer created_at column."""
    conn = AsyncMock()
    concepts = _make_ecommerce_concepts()
    concepts.customer_created_at_column = None
    dist = await _time_to_activation_distribution(conn, concepts)
    assert dist == {}


async def test_time_to_activation_query_failure():
    """Gracefully handles query errors."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=RuntimeError("query error"))
    concepts = _make_ecommerce_concepts()
    dist = await _time_to_activation_distribution(conn, concepts)
    assert dist == {}


async def test_time_to_activation_null_row():
    """Returns empty dict when fetchrow returns None."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    concepts = _make_ecommerce_concepts()
    dist = await _time_to_activation_distribution(conn, concepts)
    assert dist == {}


async def test_time_to_activation_null_median():
    """Handles null median_minutes gracefully."""
    mock_row = {
        "within_15min": 0,
        "within_30min": 0,
        "within_1hour": 0,
        "within_24hours": 0,
        "total": 0,
        "median_minutes": None,
    }
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=mock_row)
    concepts = _make_ecommerce_concepts()
    dist = await _time_to_activation_distribution(conn, concepts)
    assert dist["median_minutes"] is None


# ---------------------------------------------------------------------------
# analyze_funnel integration tests
# ---------------------------------------------------------------------------

FUNNEL_LLM_RESPONSE = {
    "stages": [
        {
            "name": "Signup",
            "table": "customers",
            "event": "account_created",
            "count": 45200,
            "description": "User creates an account",
        },
        {
            "name": "First Order",
            "table": "orders",
            "event": "first_order",
            "count": 28000,
            "description": "User places first order",
        },
        {
            "name": "Repeat Purchase",
            "table": "orders",
            "event": "repeat_order",
            "count": 12000,
            "description": "User places second order",
        },
    ],
    "biggest_dropoff": {
        "from_stage": "Signup",
        "to_stage": "First Order",
        "conversion_rate": 61.9,
        "lost_customers": 17200,
        "description": "38.1% of signups never place an order",
    },
    "activation_window": {
        "optimal_minutes": 30,
        "reasoning": "Most conversions happen within 30 minutes of signup",
    },
    "reachability": {
        "sms_reachable_in_dropoff": 6880,
        "email_reachable_in_dropoff": 17200,
        "push_reachable_in_dropoff": 0,
    },
}


async def test_analyze_funnel_ecommerce():
    """Full funnel analysis for ecommerce returns stages and dropoff."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=[45200, 28000, 20000, 0, 18000])
    conn.fetchrow = AsyncMock(
        return_value={
            "within_15min": 5000,
            "within_30min": 8000,
            "within_1hour": 12000,
            "within_24hours": 22000,
            "total": 28000,
            "median_minutes": 42.5,
        }
    )

    provider = AsyncMock()
    llm = LLMClient(provider=provider, provider_name="test")
    llm.call_json = AsyncMock(return_value=FUNNEL_LLM_RESPONSE)

    concepts = _make_ecommerce_concepts()
    funnel = await analyze_funnel(concepts, conn, llm)

    assert isinstance(funnel, Funnel)
    assert len(funnel.stages) == 3
    assert funnel.stages[0].name == "Signup"
    assert funnel.stages[1].name == "First Order"
    assert funnel.biggest_dropoff is not None
    assert funnel.biggest_dropoff.from_stage == "Signup"
    assert funnel.biggest_dropoff.conversion_rate == 61.9


async def test_analyze_funnel_saas():
    """SaaS funnel analysis includes subscription stage."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=[32000, 22000, 18000, 3200, 8000])
    conn.fetchrow = AsyncMock(
        return_value={
            "within_15min": 8000,
            "within_30min": 14000,
            "within_1hour": 18000,
            "within_24hours": 20000,
            "total": 22000,
            "median_minutes": 25.0,
        }
    )

    saas_llm_response = {
        "stages": [
            {
                "name": "Signup",
                "table": "users",
                "event": "account_created",
                "count": 32000,
                "description": "User signs up",
            },
            {
                "name": "First Feature Use",
                "table": "feature_usage",
                "event": "first_feature",
                "count": 22000,
                "description": "User uses a feature",
            },
            {
                "name": "Subscribed",
                "table": "subscriptions",
                "event": "subscription_started",
                "count": 3200,
                "description": "Org starts paying",
            },
        ],
        "biggest_dropoff": {
            "from_stage": "First Feature Use",
            "to_stage": "Subscribed",
            "conversion_rate": 14.5,
            "lost_customers": 18800,
            "description": "Most users never convert to paid",
        },
        "activation_window": {"optimal_minutes": 15, "reasoning": "SaaS users activate quickly"},
    }

    provider = AsyncMock()
    llm = LLMClient(provider=provider, provider_name="test")
    llm.call_json = AsyncMock(return_value=saas_llm_response)

    concepts = _make_saas_concepts()
    funnel = await analyze_funnel(concepts, conn, llm)

    assert len(funnel.stages) == 3
    assert funnel.biggest_dropoff.to_stage == "Subscribed"
    assert funnel.activation_window.optimal_minutes == 15


async def test_analyze_funnel_driver_service():
    """Driver service funnel includes booking and subscription stages."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=[18500, 11200, 11200, 4500, 15000])
    conn.fetchrow = AsyncMock(
        return_value={
            "within_15min": 200,
            "within_30min": 800,
            "within_1hour": 2000,
            "within_24hours": 8000,
            "total": 11200,
            "median_minutes": 120.0,
        }
    )

    driver_llm_response = {
        "stages": [
            {
                "name": "Signup",
                "table": "users",
                "event": "account_created",
                "count": 18500,
                "description": "User registers",
            },
            {
                "name": "Card Added",
                "table": "cards",
                "event": "card_added",
                "count": 14800,
                "description": "User adds payment card",
            },
            {
                "name": "First Booking",
                "table": "bookings",
                "event": "first_booking",
                "count": 11200,
                "description": "First booking made",
            },
            {
                "name": "Subscribed",
                "table": "subscriptions",
                "event": "subscribed",
                "count": 4500,
                "description": "User subscribes",
            },
        ],
        "biggest_dropoff": {
            "from_stage": "First Booking",
            "to_stage": "Subscribed",
            "conversion_rate": 40.2,
            "lost_customers": 6700,
            "description": "Many users never subscribe after first booking",
        },
        "activation_window": {"optimal_minutes": 60, "reasoning": "Driver bookings happen within an hour of signup"},
    }

    provider = AsyncMock()
    llm = LLMClient(provider=provider, provider_name="test")
    llm.call_json = AsyncMock(return_value=driver_llm_response)

    concepts = _make_driver_concepts()
    funnel = await analyze_funnel(concepts, conn, llm)

    assert len(funnel.stages) == 4
    assert funnel.biggest_dropoff.from_stage == "First Booking"


async def test_analyze_funnel_zero_customers():
    """Funnel handles zero customers without division errors."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=[0, 0, 0, 0, 0])
    conn.fetchrow = AsyncMock(return_value=None)

    empty_response = {"stages": [], "biggest_dropoff": None, "activation_window": None}

    provider = AsyncMock()
    llm = LLMClient(provider=provider, provider_name="test")
    llm.call_json = AsyncMock(return_value=empty_response)

    concepts = _make_ecommerce_concepts()
    funnel = await analyze_funnel(concepts, conn, llm)
    assert isinstance(funnel, Funnel)
    assert len(funnel.stages) == 0


async def test_analyze_funnel_activation_rate_computed():
    """The activation rate is correctly computed and passed to LLM prompt."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=[10000, 5000, 3000, 0, 4000])
    conn.fetchrow = AsyncMock(return_value=None)

    provider = AsyncMock()
    llm = LLMClient(provider=provider, provider_name="test")
    llm.call_json = AsyncMock(return_value=FUNNEL_LLM_RESPONSE)

    concepts = _make_ecommerce_concepts()

    with patch("growthclaw.discovery.funnel_analyzer.render_template", return_value="prompt") as mock_render:
        await analyze_funnel(concepts, conn, llm)
        call_kwargs = mock_render.call_args.kwargs
        assert call_kwargs["customer_count"] == 10000
        assert call_kwargs["activated_count"] == 5000
        assert call_kwargs["activation_rate"] == 50.0


async def test_analyze_funnel_passes_sms_consent_count():
    """SMS consent count is passed to the LLM prompt."""
    conn = AsyncMock()
    # Order: customers, activated, transacted, sms_consent (subscribed skipped for ecommerce—no table)
    conn.fetchval = AsyncMock(side_effect=[20000, 10000, 8000, 12000])
    conn.fetchrow = AsyncMock(return_value=None)

    provider = AsyncMock()
    llm = LLMClient(provider=provider, provider_name="test")
    llm.call_json = AsyncMock(return_value=FUNNEL_LLM_RESPONSE)

    concepts = _make_ecommerce_concepts()

    with patch("growthclaw.discovery.funnel_analyzer.render_template", return_value="prompt") as mock_render:
        await analyze_funnel(concepts, conn, llm)
        call_kwargs = mock_render.call_args.kwargs
        assert call_kwargs["sms_consent_count"] == 12000
