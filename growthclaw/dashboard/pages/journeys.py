"""Journeys dashboard page — recent journey log with filters."""

import asyncio

import asyncpg
import pandas as pd
import streamlit as st

from growthclaw.config import get_settings
from growthclaw.dashboard.queries import RECENT_JOURNEYS


async def _fetch_data(query: str) -> list[dict]:
    """Run a query against the GrowthClaw internal database."""
    settings = get_settings()
    conn = await asyncpg.connect(settings.growthclaw_database_url)
    try:
        rows = await conn.fetch(query)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def _safe_fetch(query: str) -> pd.DataFrame | None:
    """Fetch data and handle missing tables gracefully."""
    try:
        rows = asyncio.run(_fetch_data(query))
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)
    except Exception as e:
        error_msg = str(e).lower()
        if "does not exist" in error_msg or "relation" in error_msg:
            st.warning("Tables not found. Run migrations first: `growthclaw migrate`")
            return None
        st.error(f"Database error: {e}")
        return None


def _mask_user_id(user_id: str) -> str:
    """Mask user ID for privacy: show first 4 and last 2 characters."""
    s = str(user_id)
    if len(s) <= 6:
        return s[:2] + "***"
    return s[:4] + "***" + s[-2:]


def render_journeys():
    """Render the journeys page with filterable journey log."""
    st.header("Recent Journeys")

    df = _safe_fetch(RECENT_JOURNEYS)

    if df is None:
        return

    if df.empty:
        st.info("No journeys recorded yet. Run the outreach engine first.")
        return

    # Mask user IDs
    if "user_id" in df.columns:
        df["user_id"] = df["user_id"].apply(_mask_user_id)

    # Filters
    col1, col2 = st.columns(2)

    with col1:
        channels = ["All"] + sorted(df["channel"].dropna().unique().tolist())
        selected_channel = st.selectbox("Channel", channels)

    with col2:
        outcomes = ["All"] + sorted(df["outcome"].dropna().unique().tolist())
        selected_outcome = st.selectbox("Outcome", outcomes)

    # Apply filters
    filtered = df.copy()
    if selected_channel != "All":
        filtered = filtered[filtered["channel"] == selected_channel]
    if selected_outcome != "All":
        filtered = filtered[filtered["outcome"] == selected_outcome]

    st.dataframe(
        filtered,
        use_container_width=True,
        hide_index=True,
        column_config={
            "created_at": st.column_config.DatetimeColumn("Timestamp", format="YYYY-MM-DD HH:mm"),
            "user_id": "User ID",
            "trigger_name": "Trigger",
            "channel": "Channel",
            "message_preview": "Message Preview",
            "status": "Status",
            "outcome": "Outcome",
        },
    )

    st.caption(f"Showing {len(filtered)} of {len(df)} journeys")
