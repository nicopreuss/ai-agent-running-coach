# Google Calendar Runna Sessions Ingestion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest Runna training sessions from Google Calendar into a `google_calendar_runna_sessions` Supabase table, with a daily scheduler, manual API endpoint, and agent tool.

**Architecture:** `GoogleCalendarSource` follows the existing `DataSource` pattern (fetch → normalize → upsert). Events are fetched from a single calendar over a rolling 90-day window, filtered to Runna events by URL domain, then upserted by `google_event_id`. Auth uses a refresh token stored in env — scope is hardcoded to `calendar.readonly`.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0, FastAPI, APScheduler, LangChain `@tool`, Streamlit, `requests` (already installed — no new deps).

---

## File Structure

| File | Action | Purpose |
|---|---|---|
| `db/models.py` | Modify | Add `GoogleCalendarRunnaSession` ORM model |
| `ingestion/sources/google_calendar.py` | Create | `GoogleCalendarSource` — fetch, normalize, upsert |
| `ingestion/pipeline.py` | Modify | Add `google_calendar` branch to `run()` |
| `api/main.py` | Modify | Add `/ingest/google_calendar` endpoint + noon scheduler job |
| `agent/tools.py` | Modify | Add `google_calendar` to "all", fix label display |
| `ui/app.py` | Modify | Add gcal call to "Refresh All" button |
| `tests/test_gcal_model.py` | Create | Structural tests for `GoogleCalendarRunnaSession` |
| `tests/test_gcal_source.py` | Create | Unit tests for `normalize()`, `fetch()`, auth |
| `tests/test_pipeline.py` | Modify | Add `test_run_google_calendar_returns_correct_stats` |
| `tests/test_ingest_endpoints.py` | Modify | Add `test_ingest_google_calendar_returns_ok` |
| `tests/test_refresh_tool.py` | Modify | Update "all" test to cover 3 sources |
| `scripts/smoke_test_gcal_ingest.py` | Create | Manual smoke test (not in test suite) |

---

## Task 1: Feature branch + DB model

**Files:**
- Create branch: `feat/gcal-runna-ingestion`
- Modify: `db/models.py`
- Create: `tests/test_gcal_model.py`

- [ ] **Step 1: Create the feature branch and push it**

```bash
git checkout -b feat/gcal-runna-ingestion
git push -u origin feat/gcal-runna-ingestion
```

- [ ] **Step 2: Write the failing model tests**

Create `tests/test_gcal_model.py`:

```python
from db.models import GoogleCalendarRunnaSession


def test_gcal_table_name():
    assert GoogleCalendarRunnaSession.__tablename__ == "google_calendar_runna_sessions"


def test_gcal_has_required_columns():
    cols = {c.key for c in GoogleCalendarRunnaSession.__table__.columns}
    assert cols >= {"google_event_id", "date", "title", "description", "runna_url", "created_at"}


def test_gcal_primary_key_is_event_id():
    pk_cols = {c.key for c in GoogleCalendarRunnaSession.__table__.primary_key}
    assert pk_cols == {"google_event_id"}
```

- [ ] **Step 3: Run to verify the tests fail**

```bash
poetry run pytest tests/test_gcal_model.py -v
```

Expected: FAIL with `ImportError: cannot import name 'GoogleCalendarRunnaSession'`

- [ ] **Step 4: Add `GoogleCalendarRunnaSession` to `db/models.py`**

Append after the `IngestionLog` class (end of file, line 106):

```python
class GoogleCalendarRunnaSession(Base):
    __tablename__ = "google_calendar_runna_sessions"

    google_event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    runna_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 5: Run to verify tests pass**

```bash
poetry run pytest tests/test_gcal_model.py -v
```

Expected: 3 PASSED

- [ ] **Step 6: Lint check**

```bash
poetry run ruff check .
```

Expected: no errors

- [ ] **Step 7: Commit and push**

```bash
git add db/models.py tests/test_gcal_model.py
git commit -m "feat: add GoogleCalendarRunnaSession DB model"
git push
```

---

## Task 2: `GoogleCalendarSource.normalize()` — pure function

`normalize()` has no API calls — it is a pure data-transformation function. Test and implement it first, in isolation.

**Files:**
- Create: `ingestion/sources/google_calendar.py` (skeleton + `normalize` only)
- Create: `tests/test_gcal_source.py` (normalize tests)

- [ ] **Step 1: Write the failing normalize tests**

Create `tests/test_gcal_source.py`:

```python
from datetime import date

from ingestion.sources.google_calendar import GoogleCalendarSource


def _make_source() -> GoogleCalendarSource:
    """Instantiate without calling __init__ (which reads env vars)."""
    source = GoogleCalendarSource.__new__(GoogleCalendarSource)
    source._client_id = "fake_id"
    source._client_secret = "fake_secret"
    source._refresh_token = "fake_token"
    source._calendar_id = "fake_cal"
    source._access_token = "fake_access"
    source._expires_at = float("inf")
    return source


def test_normalize_filters_non_runna_events():
    raw = [
        {
            "id": "abc",
            "summary": "Dentist",
            "description": "No runna here",
            "start": {"date": "2026-05-10"},
        }
    ]
    assert _make_source().normalize(raw) == []


def test_normalize_extracts_runna_event():
    desc = "Easy run\n📲 View in the Runna app: https://club.runna.com/n9Tx/workout?dayId=abc123"
    raw = [{"id": "evt1", "summary": "Easy 5k", "description": desc, "start": {"date": "2026-05-10"}}]
    result = _make_source().normalize(raw)
    assert len(result) == 1
    assert result[0]["google_event_id"] == "evt1"
    assert result[0]["title"] == "Easy 5k"
    assert result[0]["description"] == desc
    assert result[0]["runna_url"] == "https://club.runna.com/n9Tx/workout?dayId=abc123"
    assert result[0]["date"] == date(2026, 5, 10)


def test_normalize_handles_timed_event():
    desc = "📲 View in the Runna app: https://club.runna.com/abc"
    raw = [
        {
            "id": "evt2",
            "summary": "Tempo",
            "description": desc,
            "start": {"dateTime": "2026-05-10T07:00:00+02:00"},
        }
    ]
    result = _make_source().normalize(raw)
    assert result[0]["date"] == date(2026, 5, 10)


def test_normalize_empty_input():
    assert _make_source().normalize([]) == []


def test_normalize_skips_event_with_no_description():
    raw = [{"id": "evt3", "summary": "No desc", "start": {"date": "2026-05-10"}}]
    assert _make_source().normalize(raw) == []
```

- [ ] **Step 2: Run to verify tests fail**

```bash
poetry run pytest tests/test_gcal_source.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ingestion.sources.google_calendar'`

- [ ] **Step 3: Create `ingestion/sources/google_calendar.py` with skeleton + `normalize`**

```python
"""Google Calendar data source: fetches and normalises Runna training sessions."""

import os
import re
import time
from datetime import date, datetime, timedelta, timezone

import requests
from sqlalchemy.dialects.postgresql import insert

from db.client import get_connection
from db.models import GoogleCalendarRunnaSession
from ingestion.sources.base import DataSource

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
_RUNNA_URL_RE = re.compile(r"https://club\.runna\.com\S+")
_WINDOW_DAYS = 90


class GoogleCalendarSource(DataSource):
    """Fetches Runna training sessions from a Google Calendar."""

    def __init__(self) -> None:
        self._client_id = os.environ["GOOGLE_CLIENT_ID"]
        self._client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
        self._refresh_token = os.environ["GOOGLE_REFRESH_TOKEN"]
        self._calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
        self._access_token: str | None = None
        self._expires_at: float = 0

    def fetch(self) -> list[dict]:
        raise NotImplementedError

    def normalize(self, raw: list[dict]) -> list[dict]:
        """Filter to Runna events and map to the DB schema."""
        records = []
        for event in raw:
            description = event.get("description") or ""
            if "club.runna.com" not in description:
                continue

            match = _RUNNA_URL_RE.search(description)
            runna_url = match.group(0) if match else None

            start = event.get("start", {})
            event_date: date | None = None
            if "date" in start:
                event_date = date.fromisoformat(start["date"])
            elif "dateTime" in start:
                event_date = datetime.fromisoformat(start["dateTime"]).date()

            records.append({
                "google_event_id": event["id"],
                "date": event_date,
                "title": event.get("summary"),
                "description": description,
                "runna_url": runna_url,
            })
        return records

    def upsert(self, records: list[dict]) -> int:
        raise NotImplementedError
```

- [ ] **Step 4: Run to verify normalize tests pass**

```bash
poetry run pytest tests/test_gcal_source.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: Lint check**

```bash
poetry run ruff check .
```

Expected: no errors

- [ ] **Step 6: Commit and push**

```bash
git add ingestion/sources/google_calendar.py tests/test_gcal_source.py
git commit -m "feat: add GoogleCalendarSource.normalize() with tests"
git push
```

---

## Task 3: `fetch()` and token auth

**Files:**
- Modify: `ingestion/sources/google_calendar.py` (add `_do_token_refresh`, `_ensure_valid_token`, `fetch`)
- Modify: `tests/test_gcal_source.py` (append auth + fetch tests)

- [ ] **Step 1: Append the auth and fetch tests to `tests/test_gcal_source.py`**

First, update the import line at the top of the file — replace:
```python
from datetime import date
```
with:
```python
from datetime import date
from unittest.mock import MagicMock, patch
```

Then add at the end of the file:

```python
def test_token_refresh_sends_readonly_scope():
    source = _make_source()
    source._expires_at = 0

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "new_token", "expires_in": 3600}

    with patch(
        "ingestion.sources.google_calendar.requests.post", return_value=mock_resp
    ) as mock_post:
        source._do_token_refresh()

    posted_data = mock_post.call_args.kwargs["data"]
    assert "calendar.readonly" in posted_data["scope"]
    assert source._access_token == "new_token"


def test_fetch_paginates_correctly():
    source = _make_source()

    page1 = {"items": [{"id": "evt1"}], "nextPageToken": "tok123"}
    page2 = {"items": [{"id": "evt2"}]}

    mock_r1, mock_r2 = MagicMock(), MagicMock()
    mock_r1.json.return_value = page1
    mock_r2.json.return_value = page2

    with patch(
        "ingestion.sources.google_calendar.requests.get", side_effect=[mock_r1, mock_r2]
    ):
        result = source.fetch()

    assert len(result) == 2
    assert result[0]["id"] == "evt1"
    assert result[1]["id"] == "evt2"
```

- [ ] **Step 2: Run to verify new tests fail**

```bash
poetry run pytest tests/test_gcal_source.py::test_token_refresh_sends_readonly_scope \
    tests/test_gcal_source.py::test_fetch_paginates_correctly -v
```

Expected: FAIL — `_do_token_refresh` and `fetch` are stubs (`NotImplementedError`)

- [ ] **Step 3: Implement `_do_token_refresh`, `_ensure_valid_token`, and `fetch` in `ingestion/sources/google_calendar.py`**

Replace `fetch(self)` stub and add the two auth methods. The full updated class body (replace everything from `def fetch` onward, keeping `__init__` and `normalize` unchanged):

```python
    def _do_token_refresh(self) -> None:
        response = requests.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": "https://www.googleapis.com/auth/calendar.readonly",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        self._access_token = data["access_token"]
        self._expires_at = time.time() + data["expires_in"]

    def _ensure_valid_token(self) -> str:
        if time.time() >= self._expires_at:
            self._do_token_refresh()
        return self._access_token  # type: ignore[return-value]

    def fetch(self) -> list[dict]:
        """Fetch all events in the rolling 90-day window from Google Calendar."""
        now = datetime.now(tz=timezone.utc)
        time_min = (now - timedelta(days=_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        time_max = (now + timedelta(days=_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")

        results = []
        page_token = None
        while True:
            params: dict = {
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 250,
            }
            if page_token:
                params["pageToken"] = page_token

            response = requests.get(
                f"{_CALENDAR_API_BASE}/calendars/{self._calendar_id}/events",
                headers={"Authorization": f"Bearer {self._ensure_valid_token()}"},
                params=params,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            results.extend(data.get("items", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return results
```

- [ ] **Step 4: Run all gcal source tests**

```bash
poetry run pytest tests/test_gcal_source.py -v
```

Expected: 7 PASSED

- [ ] **Step 5: Lint check**

```bash
poetry run ruff check .
```

Expected: no errors

- [ ] **Step 6: Commit and push**

```bash
git add ingestion/sources/google_calendar.py tests/test_gcal_source.py
git commit -m "feat: add GoogleCalendarSource fetch() and token auth"
git push
```

---

## Task 4: `upsert()` + pipeline integration

**Files:**
- Modify: `ingestion/sources/google_calendar.py` (replace `upsert` stub)
- Modify: `ingestion/pipeline.py` (add import + `google_calendar` branch)
- Modify: `tests/test_pipeline.py` (append new test)

- [ ] **Step 1: Append the pipeline test to `tests/test_pipeline.py`**

Add at the end of the file:

```python
def test_run_google_calendar_returns_correct_stats():
    mock_source = MagicMock()
    mock_source.fetch.return_value = [{"id": "evt1"}, {"id": "evt2"}]
    mock_source.normalize.return_value = [
        {"google_event_id": "evt1"},
        {"google_event_id": "evt2"},
    ]
    mock_source.upsert.return_value = 2

    with patch("ingestion.pipeline._read_watermark", return_value=None), \
         patch("ingestion.pipeline.GoogleCalendarSource", return_value=mock_source), \
         patch("ingestion.pipeline._write_log") as mock_log:
        result = run("google_calendar")

    assert result == {"records_fetched": 2, "records_inserted": 2, "records_skipped": 0}
    mock_log.assert_called_once_with(
        "google_calendar", IngestionStatus.success, 2, 2, 0, error=None
    )
```

- [ ] **Step 2: Run to verify the new test fails**

```bash
poetry run pytest tests/test_pipeline.py::test_run_google_calendar_returns_correct_stats -v
```

Expected: FAIL — `ValueError: Unknown source: 'google_calendar'`

- [ ] **Step 3: Implement `upsert()` in `ingestion/sources/google_calendar.py`**

Replace the `upsert` stub with:

```python
    def upsert(self, records: list[dict]) -> int:
        """Insert Runna sessions, skipping any that already exist (dedup on google_event_id)."""
        if not records:
            return 0

        with get_connection() as conn:
            stmt = (
                insert(GoogleCalendarRunnaSession)
                .values(records)
                .on_conflict_do_nothing(index_elements=["google_event_id"])
            )
            result = conn.execute(stmt)
            conn.commit()
            return result.rowcount
```

- [ ] **Step 4: Add the `google_calendar` branch to `ingestion/pipeline.py`**

Add the import at the top of the file (alongside the existing source imports):

```python
from ingestion.sources.google_calendar import GoogleCalendarSource
```

Then in `run()`, add the `elif` branch before the `else: raise ValueError` line (currently line 78):

```python
    elif source_name == "google_calendar":
        source = GoogleCalendarSource()
```

The full updated `if/elif/else` block in `run()` becomes:

```python
    if source_name == "strava":
        after_ts = int(watermark.timestamp()) if watermark else None
        source: DataSource = StravaSource(after_timestamp=after_ts)
    elif source_name == "whoop":
        start_date = watermark.strftime("%Y-%m-%dT%H:%M:%S.000Z") if watermark else None
        source = WhoopSource(start_date=start_date)
    elif source_name == "google_calendar":
        source = GoogleCalendarSource()
    else:
        raise ValueError(f"Unknown source: {source_name!r}")
```

- [ ] **Step 5: Run all pipeline tests**

```bash
poetry run pytest tests/test_pipeline.py -v
```

Expected: 6 PASSED (5 existing + 1 new)

- [ ] **Step 6: Lint check**

```bash
poetry run ruff check .
```

Expected: no errors

- [ ] **Step 7: Commit and push**

```bash
git add ingestion/sources/google_calendar.py ingestion/pipeline.py tests/test_pipeline.py
git commit -m "feat: add GoogleCalendarSource.upsert() and pipeline integration"
git push
```

---

## Task 5: API endpoint + scheduler

**Files:**
- Modify: `api/main.py` (add scheduler job + endpoint)
- Modify: `tests/test_ingest_endpoints.py` (append new test)

- [ ] **Step 1: Append the endpoint test to `tests/test_ingest_endpoints.py`**

Add at the end of the file:

```python
def test_ingest_google_calendar_returns_ok():
    result = {"records_fetched": 5, "records_inserted": 3, "records_skipped": 2}
    with patch("ingestion.pipeline.run", return_value=result):
        with TestClient(app) as client:
            response = client.post("/ingest/google_calendar")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["source"] == "google_calendar"
    assert data["records_inserted"] == 3
```

- [ ] **Step 2: Run to verify the new test fails**

```bash
poetry run pytest tests/test_ingest_endpoints.py::test_ingest_google_calendar_returns_ok -v
```

Expected: FAIL — 404 Not Found (endpoint doesn't exist yet)

- [ ] **Step 3: Add the scheduler job and endpoint to `api/main.py`**

In the `lifespan` function, add a third scheduler job after the strava job (after line 28):

```python
    _scheduler.add_job(
        lambda: pipeline.run("google_calendar"),
        CronTrigger(hour=12, minute=0, timezone="Europe/Paris"),
        id="google_calendar_daily",
        replace_existing=True,
    )
```

Add the endpoint at the end of the file:

```python
@app.post("/ingest/google_calendar", response_model=IngestResponse)
def ingest_google_calendar() -> IngestResponse:
    """Trigger an immediate Google Calendar ingestion run."""
    try:
        result = pipeline.run("google_calendar")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return IngestResponse(
        status="ok", source="google_calendar", records_inserted=result["records_inserted"]
    )
```

- [ ] **Step 4: Run all endpoint tests**

```bash
poetry run pytest tests/test_ingest_endpoints.py -v
```

Expected: 5 PASSED (4 existing + 1 new)

- [ ] **Step 5: Lint check**

```bash
poetry run ruff check .
```

Expected: no errors

- [ ] **Step 6: Commit and push**

```bash
git add api/main.py tests/test_ingest_endpoints.py
git commit -m "feat: add /ingest/google_calendar endpoint and daily scheduler job"
git push
```

---

## Task 6: Agent tool + Streamlit

**Files:**
- Modify: `agent/tools.py` (add gcal to "all", fix display labels)
- Modify: `ui/app.py` (add gcal to Refresh All button)
- Modify: `tests/test_refresh_tool.py` (update "all" test to cover 3 sources)

- [ ] **Step 1: Update the "all" test in `tests/test_refresh_tool.py`**

Replace `test_refresh_all_calls_both_sources` with:

```python
def test_refresh_all_calls_all_sources():
    responses = [
        _mock_response("whoop", 1),
        _mock_response("strava", 2),
        _mock_response("google_calendar", 0),
    ]
    with patch("agent.tools.requests.post", side_effect=responses):
        result = refresh_data.invoke({"source": "all"})

    assert "Whoop" in result
    assert "Strava" in result
    assert "Google Calendar" in result
```

- [ ] **Step 2: Run to verify the updated test fails**

```bash
poetry run pytest tests/test_refresh_tool.py::test_refresh_all_calls_all_sources -v
```

Expected: FAIL — only 2 requests made (google_calendar missing), "Google Calendar" not in result

- [ ] **Step 3: Update `agent/tools.py`**

Replace the full file contents:

```python
"""Tool definitions for the LangChain agent."""

import os

import requests
from langchain_core.tools import tool

_API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

_SOURCE_LABELS = {
    "whoop": "Whoop",
    "strava": "Strava",
    "google_calendar": "Google Calendar",
}


@tool
def refresh_data(source: str) -> str:
    """Fetch the latest data from Whoop, Strava, and/or Google Calendar and update the database.

    Use this tool when the user asks to refresh data, check if data is fresh,
    or explicitly requests pulling the latest recovery, activity, or training session records.

    Args:
        source: Which source to refresh — "whoop", "strava", "google_calendar", or "all".

    Returns:
        A plain-English summary of how many records were inserted.
    """
    sources = ["whoop", "strava", "google_calendar"] if source == "all" else [source]
    summaries = []

    for s in sources:
        response = requests.post(f"{_API_BASE_URL}/ingest/{s}", timeout=60)
        response.raise_for_status()
        data = response.json()
        n = data["records_inserted"]
        label = _SOURCE_LABELS.get(s, s.capitalize())
        if n == 0:
            summaries.append(f"{label}: already up to date.")
        elif n == 1:
            summaries.append(f"{label}: 1 new record inserted.")
        else:
            summaries.append(f"{label}: {n} new records inserted.")

    return " ".join(summaries)


def get_tools() -> list:
    """Return the list of tools registered with the agent."""
    return [refresh_data]
```

- [ ] **Step 4: Update `ui/app.py`**

Replace the sidebar block:

```python
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
```

- [ ] **Step 5: Run all refresh tool tests**

```bash
poetry run pytest tests/test_refresh_tool.py -v
```

Expected: 3 PASSED

- [ ] **Step 6: Run the full test suite**

```bash
poetry run pytest -v
```

Expected: all tests pass (existing + new)

- [ ] **Step 7: Lint check**

```bash
poetry run ruff check .
```

Expected: no errors

- [ ] **Step 8: Commit and push**

```bash
git add agent/tools.py ui/app.py tests/test_refresh_tool.py
git commit -m "feat: add google_calendar to agent refresh tool and Streamlit UI"
git push
```

---

## Task 7: Create table in Supabase + smoke test

**Files:**
- Run: `scripts/create_tables.py`
- Create: `scripts/smoke_test_gcal_ingest.py`

- [ ] **Step 1: Create the table in Supabase**

```bash
poetry run python -m scripts.create_tables
```

Expected output includes `google_calendar_runna_sessions` in the tables list:

```
Connecting to: postgresql://...
Tables created (or already exist): [..., 'google_calendar_runna_sessions', ...]
```

- [ ] **Step 2: Create the smoke test script**

Create `scripts/smoke_test_gcal_ingest.py`:

```python
"""Smoke test: fetch and display Runna sessions from Google Calendar."""

from ingestion.sources.google_calendar import GoogleCalendarSource


def main() -> None:
    print("Connecting to Google Calendar...")
    source = GoogleCalendarSource()

    raw = source.fetch()
    print(f"Fetched {len(raw)} total events from calendar (90-day window).")

    normalised = source.normalize(raw)
    print(f"Found {len(normalised)} Runna sessions.")

    for session in normalised[:5]:
        print(f"  {session['date']} — {session['title']}")
        if session["runna_url"]:
            print(f"    {session['runna_url']}")

    if len(normalised) > 5:
        print(f"  ... and {len(normalised) - 5} more.")

    inserted = source.upsert(normalised)
    print(f"Upserted: {inserted} new rows inserted.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the smoke test**

```bash
poetry run python -m scripts.smoke_test_gcal_ingest
```

Expected: lists Runna sessions from your calendar, reports inserted row count

- [ ] **Step 4: Commit and push**

```bash
git add scripts/create_tables.py scripts/smoke_test_gcal_ingest.py
git commit -m "feat: create google_calendar_runna_sessions table and add smoke test"
git push
```

- [ ] **Step 5: Open the PR**

```bash
gh pr create \
  --title "feat: Google Calendar Runna sessions ingestion" \
  --body "Ingests Runna training sessions from Google Calendar into google_calendar_runna_sessions table. Read-only calendar access enforced via hardcoded calendar.readonly scope. Daily scheduler at noon Paris time, /ingest/google_calendar endpoint, agent tool and Streamlit UI updated."
```
