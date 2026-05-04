"""Streamlit UI: metrics dashboard + chat interface for the running coach agent."""

import datetime
import os

import requests
import streamlit as st

_API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


def _recovery_colour(score: float) -> str:
    if score >= 70:
        return "#4ade80"
    if score >= 40:
        return "#facc15"
    return "#f87171"


def _fmt_duration(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_pace(sec_per_km: float) -> str:
    s = int(sec_per_km)
    return f"{s // 60}:{s % 60:02d} /km"


def _days_label(session_date: datetime.date) -> str:
    days = (session_date - datetime.date.today()).days
    if days < 0:
        return "Past"
    if days == 0:
        return "Today"
    if days == 1:
        return "Tomorrow"
    return f"In {days} days"


def _render_dashboard() -> None:
    try:
        resp = requests.get(f"{_API_BASE_URL}/dashboard/summary", timeout=10)
        resp.raise_for_status()
        summary = resp.json()
    except requests.RequestException as exc:
        st.error(f"Could not load dashboard: {exc}")
        return

    whoop = summary.get("whoop")
    last_run = summary.get("last_run")
    next_session = summary.get("next_session")

    # ── Row 1: Whoop ──────────────────────────────────────────────────────────
    st.caption("WHOOP · TODAY")
    if whoop:
        c1, c2, c3 = st.columns(3)
        colour = _recovery_colour(whoop["recovery_score"])
        c1.markdown(
            f'<p style="font-size:2rem;font-weight:bold;color:{colour};margin:0">'
            f'{whoop["recovery_score"]:.0f}%</p>'
            f'<p style="color:gray;font-size:0.8rem;margin:0">Recovery</p>',
            unsafe_allow_html=True,
        )
        c2.metric("Sleep", f'{whoop["sleep_performance_pct"]:.0f}%')
        c3.metric("Strain", f'{whoop["daily_strain"]:.1f}')
    else:
        st.caption("No Whoop data yet.")

    st.divider()

    # ── Row 2: Last Run ───────────────────────────────────────────────────────
    if last_run:
        run_date = datetime.date.fromisoformat(last_run["date"])
        st.caption(f'LAST RUN · {run_date.strftime("%a %d %b").upper()}')
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Distance", f'{last_run["distance_km"]:.1f} km')
        c2.metric("Duration", _fmt_duration(last_run["duration_seconds"]))
        c3.metric("Avg Pace", _fmt_pace(last_run["avg_pace_sec_per_km"]))
        c4.metric("Avg BPM", f'{last_run["avg_heart_rate"]:.0f}')
    else:
        st.caption("LAST RUN")
        st.caption("No run data yet.")

    st.divider()

    # ── Row 3: Next Session ───────────────────────────────────────────────────
    st.caption("NEXT SESSION")
    if next_session:
        session_date = datetime.date.fromisoformat(next_session["date"])
        st.markdown(f'**{next_session["title"]}**')
        st.caption(f'{session_date.strftime("%a %d %b")} · {_days_label(session_date)}')
    else:
        st.caption("No upcoming sessions.")


st.set_page_config(page_title="Running Coach", layout="wide")
st.title("Running Coach")

# ── Sidebar: data controls ────────────────────────────────────────────────────

with st.sidebar:
    st.header("Data")
    if st.button("Refresh All", use_container_width=True):
        with st.spinner("Syncing Whoop, Strava, and Google Calendar..."):
            try:
                whoop_res = requests.post(f"{_API_BASE_URL}/ingest/whoop", timeout=60)
                strava_res = requests.post(f"{_API_BASE_URL}/ingest/strava", timeout=60)
                gcal_res = requests.post(f"{_API_BASE_URL}/ingest/google_calendar", timeout=60)
                whoop_res.raise_for_status()
                strava_res.raise_for_status()
                gcal_res.raise_for_status()
                total = (
                    whoop_res.json()["records_inserted"]
                    + strava_res.json()["records_inserted"]
                    + gcal_res.json()["records_inserted"]
                )
                st.success(f"Synced — {total} new record{'s' if total != 1 else ''}.")
            except requests.RequestException as exc:
                st.error(f"Sync failed: {exc}")

# ── Main area ─────────────────────────────────────────────────────────────────

col_dashboard, col_chat = st.columns([3, 2])

with col_dashboard:
    st.subheader("Dashboard")
    _render_dashboard()

with col_chat:
    st.subheader("Chat")
    st.info("Agent chat will appear here in a future task.")
