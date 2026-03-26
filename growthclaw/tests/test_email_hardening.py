"""Tests for email hardening — unsubscribe injection and webhook suppression handling."""

from __future__ import annotations

from unittest.mock import AsyncMock

from growthclaw.outreach.email_sender import _inject_unsubscribe
from growthclaw.outreach.webhook_handler import (
    handle_resend_webhook,
    handle_unsubscribe_request,
)

# ---------------------------------------------------------------------------
# Unsubscribe link injection tests
# ---------------------------------------------------------------------------


def test_unsubscribe_link_injected():
    """Unsubscribe link is appended to email HTML that doesn't already have one."""
    html = "<html><body><p>Hello!</p></body></html>"
    result = _inject_unsubscribe(html, "user@example.com")
    assert "unsubscribe" in result.lower()
    assert "user%40example.com" in result or "user@example.com" in result
    # Should be inserted before </body>
    assert result.index("unsubscribe") < result.lower().index("</body>")


def test_unsubscribe_not_duplicated():
    """Unsubscribe link is NOT added when the HTML already contains one."""
    html = '<html><body><p>Hello!</p><p><a href="/unsub">Unsubscribe here</a></p></body></html>'
    result = _inject_unsubscribe(html, "user@example.com")
    # Should return the original HTML unchanged
    assert result == html


def test_unsubscribe_injected_without_body_tag():
    """Unsubscribe link is appended at end when there's no </body> tag."""
    html = "<p>Hello, no body tag here!</p>"
    result = _inject_unsubscribe(html, "test@example.com")
    assert "unsubscribe" in result.lower()
    assert result.startswith("<p>Hello")


def test_unsubscribe_case_insensitive_detection():
    """Detection of existing unsubscribe text is case-insensitive."""
    html = "<html><body><p>UNSUBSCRIBE from our list</p></body></html>"
    result = _inject_unsubscribe(html, "user@example.com")
    # Should not add another unsubscribe link
    assert result == html


# ---------------------------------------------------------------------------
# Webhook handler tests
# ---------------------------------------------------------------------------


async def test_webhook_bounce_creates_suppression():
    """Bounce webhook event creates a suppression record with reason='bounce'."""
    conn = AsyncMock()
    event = {
        "type": "email.bounced",
        "data": {"to": ["bounced@example.com"]},
    }

    await handle_resend_webhook(event, conn)

    conn.execute.assert_awaited_once()
    call_args = conn.execute.call_args[0]
    assert "INSERT INTO growthclaw.suppressions" in call_args[0]
    assert call_args[1] == "bounced@example.com"
    assert call_args[2] == "email"
    assert call_args[3] == "bounce"


async def test_webhook_complaint_creates_suppression():
    """Complaint webhook event creates a suppression record with reason='complaint'."""
    conn = AsyncMock()
    event = {
        "type": "email.complained",
        "data": {"to": ["complainer@example.com"]},
    }

    await handle_resend_webhook(event, conn)

    conn.execute.assert_awaited_once()
    call_args = conn.execute.call_args[0]
    assert "INSERT INTO growthclaw.suppressions" in call_args[0]
    assert call_args[1] == "complainer@example.com"
    assert call_args[2] == "email"
    assert call_args[3] == "complaint"


async def test_webhook_unsubscribe_creates_suppression():
    """Unsubscribe webhook event creates a suppression record with reason='unsubscribe'."""
    conn = AsyncMock()
    event = {
        "type": "email.unsubscribed",
        "data": {"to": "unsub@example.com"},
    }

    await handle_resend_webhook(event, conn)

    conn.execute.assert_awaited_once()
    call_args = conn.execute.call_args[0]
    assert "INSERT INTO growthclaw.suppressions" in call_args[0]
    assert call_args[1] == "unsub@example.com"
    assert call_args[2] == "email"
    assert call_args[3] == "unsubscribe"


async def test_webhook_unknown_type_ignored():
    """Unknown webhook event types are silently ignored."""
    conn = AsyncMock()
    event = {
        "type": "email.delivered",
        "data": {"to": ["delivered@example.com"]},
    }

    await handle_resend_webhook(event, conn)

    conn.execute.assert_not_awaited()


async def test_webhook_missing_email_skips():
    """Webhook events without a recipient email are skipped."""
    conn = AsyncMock()
    event = {
        "type": "email.bounced",
        "data": {},
    }

    await handle_resend_webhook(event, conn)

    conn.execute.assert_not_awaited()


async def test_direct_unsubscribe_request():
    """Direct unsubscribe request creates a suppression record."""
    conn = AsyncMock()

    await handle_unsubscribe_request("user@example.com", conn)

    conn.execute.assert_awaited_once()
    call_args = conn.execute.call_args[0]
    assert "INSERT INTO growthclaw.suppressions" in call_args[0]
    assert call_args[1] == "user@example.com"
    assert call_args[2] == "email"
    assert call_args[3] == "unsubscribe"
