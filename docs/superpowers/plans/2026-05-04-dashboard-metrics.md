# Dashboard Metrics Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Streamlit dashboard placeholder with a live three-row metrics panel showing today's Whoop snapshot, the latest Strava run, and the next planned Runna session.

**Architecture:** A new `api/dashboard.py` module contains three SQL query functions and the Pydantic response models. `api/main.py` registers `GET /dashboard/summary` which calls a single `get_dashboard_summary()` orchestrator. `ui/app.py` fetches the endpoint on page load and renders three metric rows using `st.columns()` + `st.metric()`, with a custom HTML block for the colour-coded recovery score.

**Tech Stack:** FastAPI, SQLAlchemy (raw `text()` queries), Pydantic v2, Streamlit, `unittest.mock`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `api/dashboard.py` | **Create** | Pydantic models, 3 query functions, orchestrator |
| `api/main.py` | **Modify** | Register `GET /dashboard/summary` route |
| `ui/app.py` | **Modify** | Replace placeholder with 3-row metric panel |
| `tests/test_dashboard_endpoint.py` | **Create** | Endpoint + colour helper tests |

---

### Task 1: `api/dashboard.py` — models, queries, orchestrator

**Files:**
- Create: `api/dashboard.py`
- Create: `tests/test_dashboard_endpoint.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dashboard_endpoint.py
import datetime
from unittest.mock import MagicMock, patch

from api.dashboard import (
    DashboardSummary,
    LastRunSnapshot,
    NextSessionSnapshot,
    WhoopSnapshot,
    get_dashboard_summary,
    get_last_run_snapshot,
    get_next_session_snapshot,
    get_whoop_snapshot,
)


def _mock_row(data: dict):
    row = MagicMock()
    row.__getitem__ = lambda self, k: data[k]
    return row


def test_get_whoop_snapshot_returns_data():
    data = {
        "recovery_score": 82.0,
        "sleep_performance_pct": 79.0,
        "daily_strain": 12.4,
        "date": datetime.date(2026, 5, 4),
    }
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = _mock_row(data)

    result = get_whoop_snapshot(conn)

    assert isinstance(result, WhoopSnapshot)
    assert result.recovery_score == 82.0
    assert result.sleep_performance_pct == 79.0
    assert result.daily_strain == 12.4
    assert result.date == datetime.date(2026, 5, 4)


def test_get_whoop_snapshot_returns_none_when_no_data():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = None

    assert get_whoop_snapshot(conn) is None


def test_get_last_run_snapshot_converts_meters_to_km():
    data = {
        "distance_meters": 8200.0,
        "duration_seconds": 2712,
        "avg_pace_sec_per_km": 330.0,
        "avg_heart_rate": 148.0,
        "date": datetime.date(2026, 5, 4),
    }
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = _mock_row(data)

    result = get_last_run_snapshot(conn)

    assert isinstance(result, LastRunSnapshot)
    assert result.distance_km == 8.2
    assert result.duration_seconds == 2712
    assert result.avg_pace_sec_per_km == 330.0
    assert result.avg_heart_rate == 148.0


def test_get_last_run_snapshot_returns_none_when_no_data():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = None

    assert get_last_run_snapshot(conn) is None


def test_get_next_session_snapshot_returns_next_upcoming():
    data = {
        "title": "Fast 8-4-2s · 8.1km",
        "date": datetime.date(2026, 5, 6),
    }
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = _mock_row(data)

    result = get_next_session_snapshot(conn)

    assert isinstance(result, NextSessionSnapshot)
    assert result.title == "Fast 8-4-2s · 8.1km"
    assert result.date == datetime.date(2026, 5, 6)


def test_get_next_session_snapshot_returns_none_when_no_data():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = None

    assert get_next_session_snapshot(conn) is None


def test_get_dashboard_summary_assembles_all_sections():
    whoop = WhoopSnapshot(
        recovery_score=82.0,
        sleep_performance_pct=79.0,
        daily_strain=12.4,
        date=datetime.date(2026, 5, 4),
    )
    run = LastRunSnapshot(
        distance_km=8.2,
        duration_seconds=2712,
        avg_pace_sec_per_km=330.0,
        avg_heart_rate=148.0,
        date=datetime.date(2026, 5, 4),
    )
    session = NextSessionSnapshot(title="Fast 8-4-2s · 8.1km", date=datetime.date(2026, 5, 6))

    mock_conn = MagicMock()
    with patch("api.dashboard.get_connection") as mock_get_conn:
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        with patch("api.dashboard.get_whoop_snapshot", return_value=whoop):
            with patch("api.dashboard.get_last_run_snapshot", return_value=run):
                with patch("api.dashboard.get_next_session_snapshot", return_value=session):
                    result = get_dashboard_summary()

    assert isinstance(result, DashboardSummary)
    assert result.whoop == whoop
    assert result.last_run == run
    assert result.next_session == session


def test_get_dashboard_summary_handles_empty_db():
    mock_conn = MagicMock()
    with patch("api.dashboard.get_connection") as mock_get_conn:
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        with patch("api.dashboard.get_whoop_snapshot", return_value=None):
            with patch("api.dashboard.get_last_run_snapshot", return_value=None):
                with patch("api.dashboard.get_next_session_snapshot", return_value=None):
                    result = get_dashboard_summary()

    assert result.whoop is None
    assert result.last_run is None
    assert result.next_session is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_dashboard_endpoint.py -v
```
Expected: `ModuleNotFoundError` or `ImportError` — `api/dashboard.py` does not exist yet.

- [ ] **Step 3: Create `api/dashboard.py`**

```python
"""Dashboard summary: query functions and response models for GET /dashboard/summary."""

import datetime

from pydantic import BaseModel
from sqlalchemy import text

from db.client import get_connection


class WhoopSnapshot(BaseModel):
    recovery_score: float
    sleep_performance_pct: float
    daily_strain: float
    date: datetime.date


class LastRunSnapshot(BaseModel):
    distance_km: float
    duration_seconds: int
    avg_pace_sec_per_km: float
    avg_heart_rate: float
    date: datetime.date


class NextSessionSnapshot(BaseModel):
    title: str
    date: datetime.date


class DashboardSummary(BaseModel):
    whoop: WhoopSnapshot | None
    last_run: LastRunSnapshot | None
    next_session: NextSessionSnapshot | None


def get_whoop_snapshot(conn) -> WhoopSnapshot | None:
    row = conn.execute(
        text(
            """
            SELECT recovery_score, sleep_performance_pct, daily_strain, date
            FROM whoop_recovery_daily
            ORDER BY date DESC
            LIMIT 1
            """
        )
    ).mappings().first()
    if row is None:
        return None
    return WhoopSnapshot(
        recovery_score=row["recovery_score"],
        sleep_performance_pct=row["sleep_performance_pct"],
        daily_strain=row["daily_strain"],
        date=row["date"],
    )


def get_last_run_snapshot(conn) -> LastRunSnapshot | None:
    row = conn.execute(
        text(
            """
            SELECT distance_meters, duration_seconds, avg_pace_sec_per_km,
                   avg_heart_rate, date
            FROM strava_activities
            ORDER BY date DESC
            LIMIT 1
            """
        )
    ).mappings().first()
    if row is None:
        return None
    return LastRunSnapshot(
        distance_km=round(row["distance_meters"] / 1000, 1),
        duration_seconds=row["duration_seconds"],
        avg_pace_sec_per_km=row["avg_pace_sec_per_km"],
        avg_heart_rate=row["avg_heart_rate"],
        date=row["date"],
    )


def get_next_session_snapshot(conn) -> NextSessionSnapshot | None:
    row = conn.execute(
        text(
            """
            SELECT title, date
            FROM google_calendar_runna_sessions
            WHERE date >= CURRENT_DATE
            ORDER BY date ASC
            LIMIT 1
            """
        )
    ).mappings().first()
    if row is None:
        return None
    return NextSessionSnapshot(title=row["title"], date=row["date"])


def get_dashboard_summary() -> DashboardSummary:
    with get_connection() as conn:
        return DashboardSummary(
            whoop=get_whoop_snapshot(conn),
            last_run=get_last_run_snapshot(conn),
            next_session=get_next_session_snapshot(conn),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_dashboard_endpoint.py -v
```
Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add api/dashboard.py tests/test_dashboard_endpoint.py
git commit -m "feat: add dashboard query functions and response models"
```

---

### Task 2: Register `GET /dashboard/summary` in `api/main.py`

**Files:**
- Modify: `api/main.py`
- Modify: `tests/test_dashboard_endpoint.py`

- [ ] **Step 1: Add the endpoint test**

Append to `tests/test_dashboard_endpoint.py`:

```python
def test_dashboard_summary_endpoint_returns_ok():
    whoop = WhoopSnapshot(
        recovery_score=82.0,
        sleep_performance_pct=79.0,
        daily_strain=12.4,
        date=datetime.date(2026, 5, 4),
    )
    run = LastRunSnapshot(
        distance_km=8.2,
        duration_seconds=2712,
        avg_pace_sec_per_km=330.0,
        avg_heart_rate=148.0,
        date=datetime.date(2026, 5, 4),
    )
    session = NextSessionSnapshot(title="Fast 8-4-2s · 8.1km", date=datetime.date(2026, 5, 6))
    summary = DashboardSummary(whoop=whoop, last_run=run, next_session=session)

    with patch("api.main.get_dashboard_summary", return_value=summary):
        from fastapi.testclient import TestClient
        from api.main import app
        with TestClient(app) as client:
            response = client.get("/dashboard/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["whoop"]["recovery_score"] == 82.0
    assert data["last_run"]["distance_km"] == 8.2
    assert data["next_session"]["title"] == "Fast 8-4-2s · 8.1km"


def test_dashboard_summary_endpoint_returns_nulls_when_empty():
    summary = DashboardSummary(whoop=None, last_run=None, next_session=None)

    with patch("api.main.get_dashboard_summary", return_value=summary):
        from fastapi.testclient import TestClient
        from api.main import app
        with TestClient(app) as client:
            response = client.get("/dashboard/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["whoop"] is None
    assert data["last_run"] is None
    assert data["next_session"] is None
```

- [ ] **Step 2: Run to verify it fails**

```bash
poetry run pytest tests/test_dashboard_endpoint.py::test_dashboard_summary_endpoint_returns_ok -v
```
Expected: FAIL — route not registered yet.

- [ ] **Step 3: Add the route to `api/main.py`**

Add this import near the top of `api/main.py` (after existing imports):

```python
from api.dashboard import DashboardSummary, get_dashboard_summary
```

Add this endpoint after the existing `/ingest/google_calendar` endpoint:

```python
@app.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary() -> DashboardSummary:
    try:
        return get_dashboard_summary()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
```

- [ ] **Step 4: Run all tests**

```bash
poetry run pytest -v
```
Expected: all tests PASS (including the 2 new endpoint tests).

- [ ] **Step 5: Commit**

```bash
git add api/main.py tests/test_dashboard_endpoint.py
git commit -m "feat: add GET /dashboard/summary endpoint"
```

---

### Task 3: Streamlit dashboard panel

**Files:**
- Modify: `ui/app.py`
- Modify: `tests/test_dashboard_endpoint.py`

- [ ] **Step 1: Write the colour helper test**

Append to `tests/test_dashboard_endpoint.py`:

```python
def test_recovery_colour_green():
    from ui.app import _recovery_colour
    assert _recovery_colour(70.0) == "#4ade80"
    assert _recovery_colour(85.0) == "#4ade80"
    assert _recovery_colour(100.0) == "#4ade80"


def test_recovery_colour_yellow():
    from ui.app import _recovery_colour
    assert _recovery_colour(40.0) == "#facc15"
    assert _recovery_colour(55.0) == "#facc15"
    assert _recovery_colour(69.9) == "#facc15"


def test_recovery_colour_red():
    from ui.app import _recovery_colour
    assert _recovery_colour(0.0) == "#f87171"
    assert _recovery_colour(39.9) == "#f87171"
```

- [ ] **Step 2: Run to verify it fails**

```bash
poetry run pytest tests/test_dashboard_endpoint.py::test_recovery_colour_green -v
```
Expected: FAIL — `_recovery_colour` not defined in `ui/app.py` yet.

- [ ] **Step 3: Replace `ui/app.py` with the full implementation**

```python
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
    return f"{seconds // 60}:{seconds % 60:02d}"


def _fmt_pace(sec_per_km: float) -> str:
    s = int(sec_per_km)
    return f"{s // 60}:{s % 60:02d} /km"


def _days_label(session_date: datetime.date) -> str:
    days = (session_date - datetime.date.today()).days
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
```

- [ ] **Step 4: Run all tests**

```bash
poetry run pytest -v
```
Expected: all tests PASS.

- [ ] **Step 5: Run ruff**

```bash
poetry run ruff check .
```
Expected: no errors. If any, fix them and re-run.

- [ ] **Step 6: Start the API and the app to verify visually**

In one terminal:
```bash
poetry run uvicorn api.main:app --reload
```

In a second terminal:
```bash
poetry run streamlit run ui/app.py
```

Open http://localhost:8501. You should see:
- Row 1: Recovery % (coloured), Sleep %, Strain
- Row 2: Distance km, Duration, Avg Pace, Avg BPM
- Row 3: Next session title + date + days label

- [ ] **Step 7: Commit**

```bash
git add ui/app.py tests/test_dashboard_endpoint.py
git commit -m "feat: implement dashboard metrics panel in Streamlit"
```
