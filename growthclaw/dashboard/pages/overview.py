"""Overview dashboard page — funnel visualization and daily sends."""

import asyncio
import json

import asyncpg
import pandas as pd
import streamlit as st

from growthclaw.config import get_settings
from growthclaw.dashboard.queries import DAILY_SENDS, FUNNEL_QUERY


async def _fetch_data(query: str) -> list[dict]:
    """Run a query against the GrowthClaw internal database."""
    settings = get_settings()
    conn = await asyncpg.connect(settings.growthclaw_database_url)
    try:
        rows = await conn.fetch(query)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def _safe_fetch(query: str) -> list[dict] | None:
    """Fetch data and handle missing tables gracefully."""
    try:
        return asyncio.run(_fetch_data(query))
    except Exception as e:
        error_msg = str(e).lower()
        if "does not exist" in error_msg or "relation" in error_msg:
            st.warning("Tables not found. Run migrations first: `growthclaw migrate`")
            return None
        st.error(f"Database error: {e}")
        return None


def render_overview():
    """Render the overview page with funnel and daily sends."""
    st.header("Overview")

    # --- Funnel ---
    st.subheader("Customer Funnel")
    rows = _safe_fetch(FUNNEL_QUERY)

    if rows is None:
        return

    if not rows:
        st.info("No discovery data yet. Run `growthclaw onboard` first.")
        return

    record = rows[0]
    funnel_data = record.get("funnel")
    concepts_data = record.get("concepts")

    # Parse JSONB if needed
    if isinstance(funnel_data, str):
        funnel_data = json.loads(funnel_data)
    if isinstance(concepts_data, str):
        concepts_data = json.loads(concepts_data)

    business_name = record.get("business_name", "")
    business_type = record.get("business_type", "")
    if business_name or business_type:
        st.caption(f"**{business_name}** — {business_type}")

    # Funnel stages as metric cards
    stages = funnel_data.get("funnel_stages") or funnel_data.get("stages", [])
    if stages:
        cols = st.columns(len(stages))
        prev_count = None
        for i, stage in enumerate(stages):
            name = stage.get("name", f"Stage {i + 1}")
            count = stage.get("count", 0)
            if prev_count and prev_count > 0:
                rate = f"{count / prev_count * 100:.1f}% conversion"
                cols[i].metric(name, f"{count:,}", delta=rate)
            else:
                cols[i].metric(name, f"{count:,}")
            prev_count = count

    # Biggest dropoff callout
    dropoff = funnel_data.get("biggest_dropoff")
    if dropoff:
        conv_rate = dropoff.get("conversion_rate", 0)
        desc = dropoff.get("description", "")
        lost = dropoff.get("lost_customers", 0)
        st.error(
            f"**Biggest Drop-off:** {dropoff.get('from_stage', '?')} → {dropoff.get('to_stage', '?')} "
            f"({conv_rate:.1%} conversion, {lost:,} lost customers)\n\n{desc}"
        )

    # Activation window
    window = funnel_data.get("activation_window")
    if window:
        st.info(
            f"**Optimal Activation Window:** {window.get('optimal_minutes', '?')} minutes — "
            f"{window.get('reasoning', '')}"
        )

    # --- Key Metrics from concepts ---
    if concepts_data:
        st.subheader("Discovered Concepts")
        col1, col2, col3 = st.columns(3)
        col1.metric("Customer Table", concepts_data.get("customer_table", "—"))
        col2.metric("Activation", concepts_data.get("activation_event", "—"))
        col3.metric("Business Type", concepts_data.get("business_type", "—"))

    # --- Daily Sends ---
    st.subheader("Daily Sends (Last 30 Days)")
    send_rows = _safe_fetch(DAILY_SENDS)

    if send_rows is None:
        return

    if not send_rows:
        st.info("No sends recorded yet. Approve triggers and run `growthclaw start`.")
    else:
        df = pd.DataFrame(send_rows)
        pivot = df.pivot_table(index="send_date", columns="channel", values="send_count", fill_value=0)
        st.bar_chart(pivot)
