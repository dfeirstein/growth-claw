"""Triggers dashboard page — trigger performance table."""

import asyncio

import asyncpg
import pandas as pd
import streamlit as st

from growthclaw.config import get_settings
from growthclaw.dashboard.queries import TRIGGER_PERFORMANCE


async def _fetch_data(query: str) -> list[dict]:
    settings = get_settings()
    conn = await asyncpg.connect(settings.growthclaw_database_url)
    try:
        rows = await conn.fetch(query)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def _safe_fetch(query: str) -> pd.DataFrame | None:
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


def render_triggers():
    """Render the triggers page with performance table."""
    st.header("Triggers")

    df = _safe_fetch(TRIGGER_PERFORMANCE)
    if df is None:
        return
    if df.empty:
        st.info("No triggers found. Run `growthclaw onboard` first.")
        return

    status_icons = {"proposed": "🟡", "approved": "🔵", "active": "🟢", "paused": "🔴"}
    df["status_display"] = df["status"].apply(lambda s: f"{status_icons.get(s, '⚪')} {s}")

    display_cols = [
        "name",
        "status_display",
        "channel",
        "delay_minutes",
        "total_fires",
        "conversions",
        "conversion_rate_pct",
    ]
    display_df = df[[c for c in display_cols if c in df.columns]].copy()

    st.dataframe(
        display_df,
        column_config={
            "name": "Trigger",
            "status_display": "Status",
            "channel": "Channel",
            "delay_minutes": "Delay (min)",
            "total_fires": "Total Fires",
            "conversions": "Conversions",
            "conversion_rate_pct": st.column_config.NumberColumn("Conv %", format="%.1f%%"),
        },
        use_container_width=True,
        hide_index=True,
    )

    st.caption("Status: 🟢 Active  🔵 Approved  🟡 Proposed  🔴 Paused")
