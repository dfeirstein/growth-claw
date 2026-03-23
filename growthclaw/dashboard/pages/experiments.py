"""Experiments dashboard page — AutoResearch cycle history and results."""

import asyncio

import asyncpg
import pandas as pd
import streamlit as st

from growthclaw.config import get_settings
from growthclaw.dashboard.queries import AUTORESEARCH_HISTORY


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


def render_experiments():
    """Render the experiments page with AutoResearch cycle history."""
    st.header("AutoResearch Experiments")

    df = _safe_fetch(AUTORESEARCH_HISTORY)

    if df is None:
        return

    if df.empty:
        st.info("No experiments have been run yet. AutoResearch cycles will appear here.")
        return

    # Summary metrics
    total_cycles = len(df)
    completed = df[df["status"] == "completed"]
    running = df[df["status"] == "running"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Cycles", total_cycles)
    col2.metric("Completed", len(completed))
    col3.metric("Running", len(running))

    if not completed.empty:
        promoted = completed[completed["decision"] == "promote_test"]
        col4.metric("Tests Promoted", len(promoted))
    else:
        col4.metric("Tests Promoted", 0)

    # Per-trigger breakdown
    st.subheader("Cycles by Trigger")

    triggers = df["trigger_name"].unique()
    selected_trigger = st.selectbox("Select Trigger", ["All"] + sorted(triggers.tolist()))

    filtered = df if selected_trigger == "All" else df[df["trigger_name"] == selected_trigger]

    # Compute conversion rates for display
    display = filtered.copy()
    display["control_rate"] = display.apply(
        lambda r: f"{r['control_converted'] / r['control_sent'] * 100:.1f}%" if r.get("control_sent", 0) > 0 else "N/A",
        axis=1,
    )
    display["test_rate"] = display.apply(
        lambda r: f"{r['test_converted'] / r['test_sent'] * 100:.1f}%" if r.get("test_sent", 0) > 0 else "N/A",
        axis=1,
    )
    display["uplift"] = display["uplift_pct"].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else "N/A")

    # Select columns for display
    display_cols = [
        "trigger_name",
        "variable",
        "control_value",
        "test_value",
        "control_rate",
        "test_rate",
        "status",
        "decision",
        "uplift",
        "confidence",
        "created_at",
    ]
    show_df = display[[c for c in display_cols if c in display.columns]].copy()
    show_df.columns = [
        "Trigger",
        "Variable",
        "Control",
        "Test",
        "Control Rate",
        "Test Rate",
        "Status",
        "Decision",
        "Uplift",
        "Confidence",
        "Started",
    ]

    st.dataframe(
        show_df,
        use_container_width=True,
        hide_index=True,
    )

    # Detail view for completed cycles
    if not completed.empty and selected_trigger != "All":
        st.subheader("Conversion Rate Comparison")
        trigger_completed = completed[completed["trigger_name"] == selected_trigger]
        if not trigger_completed.empty:
            chart_data = pd.DataFrame(
                {
                    "Cycle": trigger_completed["cycle_id"].astype(str),
                    "Control": trigger_completed.apply(
                        lambda r: (
                            r["control_converted"] / r["control_sent"] * 100 if r.get("control_sent", 0) > 0 else 0
                        ),
                        axis=1,
                    ),
                    "Test": trigger_completed.apply(
                        lambda r: r["test_converted"] / r["test_sent"] * 100 if r.get("test_sent", 0) > 0 else 0,
                        axis=1,
                    ),
                }
            ).set_index("Cycle")
            st.bar_chart(chart_data)

    # Show reasoning for most recent completed cycle
    if not completed.empty:
        st.subheader("Latest Evaluation")
        latest = completed.iloc[0]
        st.markdown(f"**Variable:** {latest.get('variable', 'N/A')}")
        st.markdown(f"**Decision:** {latest.get('decision', 'N/A')}")
        st.markdown(f"**Reasoning:** {latest.get('reasoning', 'N/A')}")
