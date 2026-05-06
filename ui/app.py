"""Streamlit UI: metrics dashboard + chat interface for the running coach agent."""

import datetime
import html
import os

import requests
import streamlit as st
import streamlit.components.v1 as components

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
        c1, c2, c3 = st.columns(3)
        c1.metric("Distance", f'{last_run["distance_km"]:.1f} km')
        c2.metric("Duration", _fmt_duration(last_run["duration_seconds"]))
        c3.metric("Avg Pace", _fmt_pace(last_run["avg_pace_sec_per_km"]))
        c4, c5 = st.columns(2)
        c4.metric("Avg BPM", f'{last_run["avg_heart_rate"]:.0f}')
        ef = last_run.get("efficiency_factor")
        c5.metric("EF", f"{ef:.2f}" if ef is not None else "N/A")
    else:
        st.caption("LAST RUN")
        st.caption("No run data yet.")

    st.divider()

    # ── Row 3: Next Session ───────────────────────────────────────────────────
    if next_session:
        session_date = datetime.date.fromisoformat(next_session["date"])
        st.caption(
            f'NEXT SESSION · {session_date.strftime("%a %d %b").upper()}'
            f' · {_days_label(session_date)}'
        )
        st.markdown(f'**{next_session["title"]}**')
        if next_session.get("description"):
            st.caption(next_session["description"])
    else:
        st.caption("No upcoming sessions.")

    st.divider()

    # ── Row 4: Weekly EF ──────────────────────────────────────────────────────
    st.caption("WEEKLY EFFICIENCY FACTOR · LAST 3 MONTHS")
    try:
        resp = requests.get(f"{_API_BASE_URL}/dashboard/weekly-ef", timeout=10)
        resp.raise_for_status()
        points = resp.json()
    except requests.RequestException as exc:
        st.error(f"Could not load weekly EF: {exc}")
        points = []

    if points:
        import altair as alt
        import pandas as pd

        df = pd.DataFrame(points)
        df["week_start"] = pd.to_datetime(df["week_start"])
        chart = (
            alt.Chart(df)
            .mark_line(color="#4ade80", point=alt.OverlayMarkDef(color="#4ade80", size=50))
            .encode(
                x=alt.X("week_start:T", title="Week", axis=alt.Axis(format="%b %d")),
                y=alt.Y("weekly_ef:Q", title="EF", scale=alt.Scale(zero=False)),
                tooltip=[
                    alt.Tooltip("week_start:T", title="Week", format="%b %d"),
                    alt.Tooltip("weekly_ef:Q", title="EF", format=".2f"),
                ],
            )
            .properties(height=200)
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.caption("No efficiency data yet.")


def _render_chat() -> None:
    """Render the chat panel: session history as bubbles, tool chips, and the input box."""
    if "messages" not in st.session_state:
        st.session_state.messages = []

    with st.container(height=650):
        for msg in st.session_state.messages:
            if msg["role"] == "user":
                with st.chat_message("user"):
                    st.markdown(msg["content"])
            else:
                if msg["tools_used"]:
                    chips_html = " ".join(
                        f'<span style="background:#1e3a2a;border:1px solid #2a5a3a;'
                        f'border-radius:12px;padding:3px 8px;color:#4aaa6a;'
                        f'font-size:0.75rem;">🔧 {html.escape(tool)}</span>'
                        for tool in msg["tools_used"]
                    )
                    st.markdown(
                        f'<div style="margin:4px 0 8px 0">{chips_html}</div>',
                        unsafe_allow_html=True,
                    )
                with st.chat_message("assistant"):
                    st.markdown(msg["content"])

    # Scroll chat box to bottom. Targets an internal Streamlit testid — verify on major upgrades.
    components.html(
        """
        <script>
        const containers = window.parent.document.querySelectorAll(
            '[data-testid="stVerticalBlockBorderWrapper"]'
        );
        if (containers.length > 0) {
            const chatBox = containers[containers.length - 1];
            chatBox.scrollTop = chatBox.scrollHeight;
        }
        </script>
        """,
        height=0,
    )

    if query := st.chat_input("Ask your coach..."):
        st.session_state.messages.append(
            {"role": "user", "content": query, "tools_used": []}
        )
        with st.spinner("Thinking..."):
            try:
                resp = requests.post(
                    f"{_API_BASE_URL}/chat",
                    json={"query": query},
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": data["response"],
                    "tools_used": data.get("tools_used", []),
                })
            except requests.RequestException as exc:
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"Sorry, I couldn't reach the coach. Is the API running? ({exc})",
                    "tools_used": [],
                })
        st.rerun()


st.set_page_config(page_title="Running Coach", layout="wide")

st.markdown(
    """
    <style>
    .main > .block-container { padding-bottom: 0rem; }
    section.main { overflow: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

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
    _render_chat()
