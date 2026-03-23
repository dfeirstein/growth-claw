"""GrowthClaw Streamlit dashboard — main entry point."""

import streamlit as st

from growthclaw.dashboard.pages.experiments import render_experiments
from growthclaw.dashboard.pages.journeys import render_journeys
from growthclaw.dashboard.pages.overview import render_overview
from growthclaw.dashboard.pages.triggers import render_triggers

st.set_page_config(page_title="GrowthClaw", layout="wide")

st.title("GrowthClaw Dashboard")

# Sidebar navigation
page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Triggers", "Journeys", "Experiments"],
    index=0,
)

if page == "Overview":
    render_overview()
elif page == "Triggers":
    render_triggers()
elif page == "Journeys":
    render_journeys()
elif page == "Experiments":
    render_experiments()
