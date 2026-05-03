"""Streamlit UI: metrics dashboard + chat interface for the running coach agent."""

import os

import requests
import streamlit as st

_API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Running Coach", layout="wide")
st.title("Running Coach")

# ── Sidebar: data controls ────────────────────────────────────────────────────

with st.sidebar:
    st.header("Data")
    if st.button("Refresh All", use_container_width=True):
        with st.spinner("Syncing Whoop and Strava..."):
            try:
                whoop_res = requests.post(f"{_API_BASE_URL}/ingest/whoop", timeout=60)
                strava_res = requests.post(f"{_API_BASE_URL}/ingest/strava", timeout=60)
                whoop_res.raise_for_status()
                strava_res.raise_for_status()
                total = (
                    whoop_res.json()["records_inserted"]
                    + strava_res.json()["records_inserted"]
                )
                st.success(f"Synced — {total} new record{'s' if total != 1 else ''}.")
            except requests.RequestException as exc:
                st.error(f"Sync failed: {exc}")

# ── Main area: placeholder panels ────────────────────────────────────────────

col_dashboard, col_chat = st.columns([3, 2])

with col_dashboard:
    st.subheader("Dashboard")
    st.info("Charts will appear here in a future task.")

with col_chat:
    st.subheader("Chat")
    st.info("Agent chat will appear here in a future task.")
