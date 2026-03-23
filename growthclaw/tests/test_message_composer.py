"""Tests for message_composer — verifies SMS length limits and LLM-based message generation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from growthclaw.llm.client import LLMClient
from growthclaw.models.profile import IntelligenceBrief
from growthclaw.models.schema_map import BusinessConcepts
from growthclaw.models.trigger import TriggerRule
from growthclaw.outreach.message_composer import SMS_MAX_LENGTH, compose


def _make_concepts(business_type: str = "ecommerce") -> BusinessConcepts:
    """Create a minimal BusinessConcepts."""
    return BusinessConcepts(
        business_type=business_type,
        business_description="Test business",
        customer_table="users",
        customer_id_column="id",
    )


def _make_trigger(channel: str = "sms") -> TriggerRule:
    """Create a test TriggerRule."""
    return TriggerRule(
        name="test_trigger",
        description="Nudge user to complete first purchase",
        watch_table="users",
        watch_event="INSERT",
        check_sql="SELECT TRUE",
        channel=channel,
        message_context="User signed up but hasn't made a purchase yet",
    )


def _make_brief() -> IntelligenceBrief:
    """Create a test IntelligenceBrief."""
    return IntelligenceBrief(
        summary="New user who signed up 30 minutes ago from Google Ads",
        customer_segment="new_user",
        engagement_level="low",
        key_facts=["Signed up via Google Ads", "No purchases yet", "Has phone on file"],
        recommended_tone="friendly and encouraging",
        recommended_cta="Complete first purchase",
        risk_factors=["May churn if not engaged quickly"],
    )


def _make_profile() -> dict:
    """Create a test profile dict."""
    return {
        "basic_info": [{"first_name": "Alice", "email": "alice@example.com", "created_at": "2024-12-15"}],
        "orders": [],
    }


def _make_mock_llm(responses: list[str]) -> LLMClient:
    """Create a mock LLMClient that returns the given responses in sequence."""
    provider = AsyncMock()
    client = LLMClient(provider=provider, provider_name="test")
    client.call = AsyncMock(side_effect=responses)
    return client


# ---------------------------------------------------------------------------
# SMS length tests
# ---------------------------------------------------------------------------


async def test_sms_under_160_chars():
    """SMS message under 160 chars is returned as-is."""
    short_msg = "Hi Alice! Complete your first order and get 10% off: https://shop.co/go"
    llm = _make_mock_llm([short_msg])

    result = await compose(
        trigger=_make_trigger("sms"),
        profile_data=_make_profile(),
        intelligence_brief=_make_brief(),
        concepts=_make_concepts(),
        llm_client=llm,
        cta_link="https://shop.co/go",
        business_name="TestShop",
    )

    assert len(result) <= SMS_MAX_LENGTH
    assert result == short_msg


async def test_sms_exactly_160_chars():
    """SMS message of exactly 160 chars is valid."""
    msg_160 = "A" * 160
    llm = _make_mock_llm([msg_160])

    result = await compose(
        trigger=_make_trigger("sms"),
        profile_data=_make_profile(),
        intelligence_brief=_make_brief(),
        concepts=_make_concepts(),
        llm_client=llm,
    )

    assert len(result) == 160


async def test_sms_too_long_retries():
    """LLM is re-prompted when SMS exceeds 160 chars, and succeeds on retry."""
    long_msg = "A" * 200
    short_msg = "Hi Alice! Your first order awaits: https://shop.co/go"
    llm = _make_mock_llm([long_msg, short_msg])

    result = await compose(
        trigger=_make_trigger("sms"),
        profile_data=_make_profile(),
        intelligence_brief=_make_brief(),
        concepts=_make_concepts(),
        llm_client=llm,
    )

    assert len(result) <= SMS_MAX_LENGTH
    assert llm.call.call_count == 2


async def test_sms_truncated_after_max_retries():
    """SMS is truncated with '...' when LLM fails to shorten after max retries."""
    long_msg = "B" * 250
    still_long = "C" * 200
    also_long = "D" * 180
    llm = _make_mock_llm([long_msg, still_long, also_long])

    result = await compose(
        trigger=_make_trigger("sms"),
        profile_data=_make_profile(),
        intelligence_brief=_make_brief(),
        concepts=_make_concepts(),
        llm_client=llm,
    )

    assert len(result) <= SMS_MAX_LENGTH
    assert result.endswith("...")


async def test_sms_strips_quotes():
    """Quotes around the message are stripped."""
    quoted_msg = '"Hi Alice! Check out our sale: https://shop.co/go"'
    llm = _make_mock_llm([quoted_msg])

    result = await compose(
        trigger=_make_trigger("sms"),
        profile_data=_make_profile(),
        intelligence_brief=_make_brief(),
        concepts=_make_concepts(),
        llm_client=llm,
    )

    assert not result.startswith('"')
    assert not result.endswith('"')


async def test_sms_strips_single_quotes():
    """Single quotes around the message are stripped."""
    quoted_msg = "'Hey Alice, your ride awaits: https://app.co/go'"
    llm = _make_mock_llm([quoted_msg])

    result = await compose(
        trigger=_make_trigger("sms"),
        profile_data=_make_profile(),
        intelligence_brief=_make_brief(),
        concepts=_make_concepts(),
        llm_client=llm,
    )

    assert not result.startswith("'")
    assert not result.endswith("'")


async def test_sms_strips_whitespace():
    """Leading/trailing whitespace is stripped."""
    padded_msg = "  Hi Alice! Order now: https://shop.co  "
    llm = _make_mock_llm([padded_msg])

    result = await compose(
        trigger=_make_trigger("sms"),
        profile_data=_make_profile(),
        intelligence_brief=_make_brief(),
        concepts=_make_concepts(),
        llm_client=llm,
    )

    assert not result.startswith(" ")
    assert not result.endswith(" ")


# ---------------------------------------------------------------------------
# Email channel tests (no 160-char limit)
# ---------------------------------------------------------------------------


async def test_email_allows_long_messages():
    """Email messages are not subject to the 160-char SMS limit."""
    long_email = "Dear Alice,\n\n" + "Thank you for signing up! " * 20 + "\n\nBest,\nTestShop"
    llm = _make_mock_llm([long_email])

    result = await compose(
        trigger=_make_trigger("email"),
        profile_data=_make_profile(),
        intelligence_brief=_make_brief(),
        concepts=_make_concepts(),
        llm_client=llm,
    )

    assert len(result) > SMS_MAX_LENGTH
    assert result == long_email.strip()
    # Only one LLM call, no retries for length
    assert llm.call.call_count == 1


async def test_email_still_strips_quotes():
    """Email messages have quotes stripped too."""
    quoted_email = '"Welcome to TestShop, Alice! Here is your getting started guide..."'
    llm = _make_mock_llm([quoted_email])

    result = await compose(
        trigger=_make_trigger("email"),
        profile_data=_make_profile(),
        intelligence_brief=_make_brief(),
        concepts=_make_concepts(),
        llm_client=llm,
    )

    assert not result.startswith('"')
    assert not result.endswith('"')


# ---------------------------------------------------------------------------
# LLM interaction tests
# ---------------------------------------------------------------------------


async def test_compose_uses_creative_temperature():
    """Message composition uses a higher temperature for creativity."""
    short_msg = "Hi Alice! Shop now: https://shop.co"
    llm = _make_mock_llm([short_msg])

    await compose(
        trigger=_make_trigger("sms"),
        profile_data=_make_profile(),
        intelligence_brief=_make_brief(),
        concepts=_make_concepts(),
        llm_client=llm,
    )

    call_kwargs = llm.call.call_args
    assert call_kwargs.kwargs.get("temperature", 0) == 0.7


async def test_compose_passes_business_name():
    """Business name is used in the prompt template context."""
    short_msg = "Welcome to DriverCo! Book your first ride: https://app.co"
    provider = AsyncMock()
    llm = LLMClient(provider=provider, provider_name="test")
    llm.call = AsyncMock(return_value=short_msg)

    with patch("growthclaw.outreach.message_composer.render_template", return_value="mock prompt") as mock_render:
        await compose(
            trigger=_make_trigger("sms"),
            profile_data=_make_profile(),
            intelligence_brief=_make_brief(),
            concepts=_make_concepts("driver_service"),
            llm_client=llm,
            cta_link="https://app.co",
            business_name="DriverCo",
        )
        call_kwargs = mock_render.call_args.kwargs
        assert call_kwargs["business_name"] == "DriverCo"
        assert call_kwargs["cta_link"] == "https://app.co"


async def test_compose_includes_trigger_context():
    """Trigger context and description are passed to the prompt."""
    short_msg = "Complete your setup!"
    provider = AsyncMock()
    llm = LLMClient(provider=provider, provider_name="test")
    llm.call = AsyncMock(return_value=short_msg)

    trigger = _make_trigger("sms")

    with patch("growthclaw.outreach.message_composer.render_template", return_value="mock prompt") as mock_render:
        await compose(
            trigger=trigger,
            profile_data=_make_profile(),
            intelligence_brief=_make_brief(),
            concepts=_make_concepts(),
            llm_client=llm,
        )
        call_kwargs = mock_render.call_args.kwargs
        assert call_kwargs["trigger_context"] == trigger.message_context
        assert call_kwargs["trigger_description"] == trigger.description


async def test_retry_prompt_includes_char_count():
    """When retrying, the retry prompt mentions the current length and limit."""
    long_msg = "X" * 200
    short_msg = "Short msg: go.co"
    llm = _make_mock_llm([long_msg, short_msg])

    await compose(
        trigger=_make_trigger("sms"),
        profile_data=_make_profile(),
        intelligence_brief=_make_brief(),
        concepts=_make_concepts(),
        llm_client=llm,
    )

    retry_call = llm.call.call_args_list[1]
    retry_prompt = retry_call[0][0]
    assert "200" in retry_prompt  # mentions current length
    assert "160" in retry_prompt  # mentions limit


# ---------------------------------------------------------------------------
# Edge case: different business types
# ---------------------------------------------------------------------------


async def test_compose_for_driver_service():
    """Message can be composed for a driver service business."""
    msg = "Hi Michael! Book your first ride with DriverCo: https://app.co/go"
    llm = _make_mock_llm([msg])

    result = await compose(
        trigger=_make_trigger("sms"),
        profile_data={
            "user_info": [{"first_name": "Michael", "phone": "+12125551234"}],
            "bookings": [],
        },
        intelligence_brief=IntelligenceBrief(
            summary="New member with no bookings",
            customer_segment="new_member",
            engagement_level="none",
            recommended_tone="warm and premium",
            recommended_cta="Book first ride",
        ),
        concepts=_make_concepts("driver_service"),
        llm_client=llm,
        cta_link="https://app.co/go",
        business_name="DriverCo",
    )

    assert len(result) <= SMS_MAX_LENGTH
    assert "Michael" in result


async def test_compose_for_saas():
    """Message can be composed for a SaaS business."""
    msg = "Hi Jane! Try our dashboard: https://app.saas.co/start"
    llm = _make_mock_llm([msg])

    result = await compose(
        trigger=_make_trigger("sms"),
        profile_data={
            "user_info": [{"full_name": "Jane Doe", "email": "jane@acme.com"}],
            "feature_usage": [],
        },
        intelligence_brief=IntelligenceBrief(
            summary="New SaaS user, no feature usage yet",
            customer_segment="trial_user",
            engagement_level="none",
            recommended_tone="professional",
            recommended_cta="Explore dashboard",
        ),
        concepts=_make_concepts("saas"),
        llm_client=llm,
        cta_link="https://app.saas.co/start",
        business_name="SaaSApp",
    )

    assert len(result) <= SMS_MAX_LENGTH
