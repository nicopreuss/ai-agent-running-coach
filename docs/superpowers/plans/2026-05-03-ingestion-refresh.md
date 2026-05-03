# Ingestion Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire incremental ingestion for Whoop and Strava so data stays fresh via a daily schedule, a Streamlit "Refresh All" button, and an agent tool.

**Architecture:** APScheduler runs inside FastAPI and fires two cron jobs (Whoop at 09:00 Paris, Strava at 20:00 Paris). Both the scheduler and two new `POST /ingest/{source}` endpoints call the same `pipeline.run(source_name)` function, which reads a watermark from the new `ingestion_log` table, fetches only new data, and writes a log entry on completion. A `refresh_data` LangChain tool calls those endpoints so the agent can trigger ingestion on demand. A Streamlit app provides the UI.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0, FastAPI 0.111, APScheduler 3.10, LangChain, Streamlit

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `db/models.py` | Modify | Add `IngestionSource` enum, `IngestionStatus` enum, `IngestionLog` model |
| `ingestion/pipeline.py` | Modify | Add `_read_watermark()`, `_write_log()`, `run(source_name)` |
| `api/main.py` | Modify | Add APScheduler lifespan, `POST /ingest/whoop`, `POST /ingest/strava` |
| `agent/tools.py` | Modify | Replace placeholder with `refresh_data` tool, update `get_tools()` |
| `ui/app.py` | Create | Streamlit app with "Refresh All" button |
| `ui/__init__.py` | Create | Empty package marker |
| `scripts/seed_ingestion_log.py` | Create | One-time seed: write bootstrap watermarks so first incremental run doesn't re-fetch all history |
| `pyproject.toml` | Modify | Add `streamlit` dependency |
| `tests/test_ingestion_log_model.py` | Create | Structural test for `IngestionLog` columns |
| `tests/test_pipeline.py` | Create | Unit tests for `_read_watermark()` and `run()` |
| `tests/test_ingest_endpoints.py` | Create | FastAPI TestClient tests for ingest endpoints |
| `tests/test_refresh_tool.py` | Create | Unit test for `refresh_data` agent tool |

---

## Task 1: Add `IngestionLog` SQLAlchemy model

**Files:**
- Modify: `db/models.py`
- Test: `tests/test_ingestion_log_model.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ingestion_log_model.py`:

```python
from db.models import IngestionLog, IngestionSource, IngestionStatus


def test_ingestion_log_table_name():
    assert IngestionLog.__tablename__ == "ingestion_log"


def test_ingestion_log_has_required_columns():
    cols = {c.key for c in IngestionLog.__table__.columns}
    assert cols >= {"id", "source", "status", "records_fetched", "records_inserted",
                    "records_skipped", "last_fetched_at", "error_message", "created_at"}


def test_ingestion_source_enum_values():
    assert IngestionSource.whoop.value == "whoop"
    assert IngestionSource.strava.value == "strava"


def test_ingestion_status_enum_values():
    assert IngestionStatus.success.value == "success"
    assert IngestionStatus.failed.value == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_ingestion_log_model.py -v
```

Expected: `ImportError: cannot import name 'IngestionLog'`

- [ ] **Step 3: Add the model to `db/models.py`**

Add at the top of `db/models.py`, after existing imports:

```python
import enum

from sqlalchemy import Enum as SAEnum
```

Then add these three classes after `WhoopRecoveryDaily`:

```python
class IngestionSource(enum.Enum):
    whoop = "whoop"
    strava = "strava"


class IngestionStatus(enum.Enum):
    success = "success"
    partial = "partial"
    failed = "failed"


class IngestionLog(Base):
    __tablename__ = "ingestion_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[IngestionSource] = mapped_column(
        SAEnum(IngestionSource, native_enum=False), nullable=False
    )
    status: Mapped[IngestionStatus] = mapped_column(
        SAEnum(IngestionStatus, native_enum=False), nullable=False
    )
    records_fetched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_inserted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_skipped: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
poetry run pytest tests/test_ingestion_log_model.py -v
```

Expected: 4 tests PASSED

- [ ] **Step 5: Create the table in the database**

```bash
poetry run python -m scripts.create_tables
```

Expected output includes `ingestion_log` in the tables list.

- [ ] **Step 6: Create `scripts/seed_ingestion_log.py`**

```python
"""One-time seed: write bootstrap ingestion_log entries so the first incremental
run fetches only recent data rather than re-fetching all history."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from db.client import get_connection, get_engine
from db.models import Base, IngestionLog, IngestionSource, IngestionStatus
from sqlalchemy.dialects.postgresql import insert


def main() -> None:
    Base.metadata.create_all(get_engine())
    watermark = datetime.now(tz=timezone.utc) - timedelta(days=3)

    with get_connection() as conn:
        for source in IngestionSource:
            existing = conn.execute(
                select(IngestionLog.id)
                .where(IngestionLog.source == source)
                .limit(1)
            ).scalar_one_or_none()

            if existing:
                print(f"Skipping {source.value} — log entry already exists.")
                continue

            conn.execute(
                insert(IngestionLog).values([{
                    "id": uuid.uuid4(),
                    "source": source,
                    "status": IngestionStatus.success,
                    "records_fetched": 0,
                    "records_inserted": 0,
                    "records_skipped": 0,
                    "last_fetched_at": watermark,
                    "error_message": None,
                }])
            )
            print(f"Seeded {source.value} with watermark {watermark.isoformat()}")

        conn.commit()


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run the seed script**

```bash
poetry run python -m scripts.seed_ingestion_log
```

Expected: prints `Seeded whoop with watermark ...` and `Seeded strava with watermark ...`

- [ ] **Step 8: Commit**

```bash
git add db/models.py tests/test_ingestion_log_model.py scripts/seed_ingestion_log.py
git commit -m "feat: add IngestionLog model and seed script"
```

---

## Task 2: Add watermark-aware `run()` to `ingestion/pipeline.py`

**Files:**
- Modify: `ingestion/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pipeline.py`:

```python
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from ingestion.pipeline import _read_watermark, run


def _mock_connection(scalar_result=None):
    """Return a mock context-manager connection that returns scalar_result on execute."""
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.scalar_one_or_none.return_value = scalar_result
    return conn


def test_read_watermark_returns_none_when_no_log():
    with patch("ingestion.pipeline.get_connection", return_value=_mock_connection(None)):
        result = _read_watermark("strava")
    assert result is None


def test_read_watermark_returns_timestamp_from_log():
    ts = datetime(2026, 5, 1, 8, 0, 0, tzinfo=timezone.utc)
    with patch("ingestion.pipeline.get_connection", return_value=_mock_connection(ts)):
        result = _read_watermark("whoop")
    assert result == ts


def test_run_strava_returns_correct_stats():
    mock_source = MagicMock()
    mock_source.fetch.return_value = [{"id": 1}, {"id": 2}]
    mock_source.normalize.return_value = [{"strava_activity_id": 1}, {"strava_activity_id": 2}]
    mock_source.upsert.return_value = 1  # 1 inserted, 1 skipped (already exists)

    with patch("ingestion.pipeline._read_watermark", return_value=None), \
         patch("ingestion.pipeline.StravaSource", return_value=mock_source), \
         patch("ingestion.pipeline._write_log") as mock_log:
        result = run("strava")

    assert result == {"records_fetched": 2, "records_inserted": 1, "records_skipped": 1}
    mock_log.assert_called_once_with("strava", "success", 2, 1, 1, error=None)


def test_run_whoop_returns_correct_stats():
    mock_source = MagicMock()
    mock_source.fetch.return_value = [{"cycle": {}}]
    mock_source.normalize.return_value = [{"date": "2026-05-01"}]
    mock_source.upsert.return_value = 1

    with patch("ingestion.pipeline._read_watermark", return_value=None), \
         patch("ingestion.pipeline.WhoopSource", return_value=mock_source), \
         patch("ingestion.pipeline._write_log") as mock_log:
        result = run("whoop")

    assert result == {"records_fetched": 1, "records_inserted": 1, "records_skipped": 0}
    mock_log.assert_called_once_with("whoop", "success", 1, 1, 0, error=None)


def test_run_writes_failed_log_on_exception():
    mock_source = MagicMock()
    mock_source.fetch.side_effect = RuntimeError("API down")

    with patch("ingestion.pipeline._read_watermark", return_value=None), \
         patch("ingestion.pipeline.StravaSource", return_value=mock_source), \
         patch("ingestion.pipeline._write_log") as mock_log:
        try:
            run("strava")
        except RuntimeError:
            pass

    mock_log.assert_called_once_with("strava", "failed", 0, 0, 0, error="API down")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_pipeline.py -v
```

Expected: `ImportError: cannot import name '_read_watermark'`

- [ ] **Step 3: Rewrite `ingestion/pipeline.py` with watermark support**

Replace the entire file:

```python
"""Ingestion pipeline: orchestrates fetch → normalize → upsert for each data source."""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert

from db.client import get_connection
from db.models import IngestionLog, IngestionSource, IngestionStatus
from ingestion.sources.base import DataSource
from ingestion.sources.strava import StravaSource
from ingestion.sources.whoop import WhoopSource

logger = logging.getLogger(__name__)


def _read_watermark(source_name: str) -> datetime | None:
    """Return last_fetched_at from the most recent successful ingestion for this source."""
    with get_connection() as conn:
        stmt = (
            select(IngestionLog.last_fetched_at)
            .where(IngestionLog.source == IngestionSource(source_name))
            .where(IngestionLog.status == IngestionStatus.success)
            .order_by(desc(IngestionLog.created_at))
            .limit(1)
        )
        return conn.execute(stmt).scalar_one_or_none()


def _write_log(
    source_name: str,
    status: str,
    fetched: int,
    inserted: int,
    skipped: int,
    error: str | None = None,
) -> None:
    """Write an ingestion_log row. On success, sets last_fetched_at to now."""
    now = datetime.now(tz=timezone.utc)
    record = {
        "id": uuid.uuid4(),
        "source": IngestionSource(source_name),
        "status": IngestionStatus(status),
        "records_fetched": fetched,
        "records_inserted": inserted,
        "records_skipped": skipped,
        "last_fetched_at": now if status == "success" else None,
        "error_message": error,
    }
    with get_connection() as conn:
        conn.execute(insert(IngestionLog).values([record]))
        conn.commit()


def run(source_name: str) -> dict:
    """Run incremental ingestion for one source using the watermark from ingestion_log.

    Args:
        source_name: "strava" or "whoop"

    Returns:
        dict with records_fetched, records_inserted, records_skipped
    """
    logger.info("Starting ingestion for source: %s", source_name)

    watermark = _read_watermark(source_name)
    logger.info("Watermark for %s: %s", source_name, watermark)

    if source_name == "strava":
        after_ts = int(watermark.timestamp()) if watermark else None
        source: DataSource = StravaSource(after_timestamp=after_ts)
    elif source_name == "whoop":
        start_date = watermark.strftime("%Y-%m-%dT%H:%M:%S.000Z") if watermark else None
        source = WhoopSource(start_date=start_date)
    else:
        raise ValueError(f"Unknown source: {source_name!r}")

    try:
        raw = source.fetch()
        logger.info("Fetched %d raw records from %s", len(raw), source_name)

        normalised = source.normalize(raw)
        inserted = source.upsert(normalised)
        skipped = len(normalised) - inserted

        logger.info("Upserted %d records (%d skipped) for %s", inserted, skipped, source_name)
        _write_log(source_name, "success", len(raw), inserted, skipped, error=None)

        return {"records_fetched": len(raw), "records_inserted": inserted, "records_skipped": skipped}

    except Exception as exc:
        logger.exception("Ingestion failed for %s: %s", source_name, exc)
        _write_log(source_name, "failed", 0, 0, 0, error=str(exc))
        raise


def run_pipeline(sources: list[DataSource]) -> None:
    """Execute the full ingestion pipeline for every provided source.

    Args:
        sources: List of DataSource instances to run in sequence.
    """
    for source in sources:
        name = type(source).__name__
        logger.info("Starting ingestion for source: %s", name)

        raw = source.fetch()
        logger.info("Fetched %d raw records from %s", len(raw), name)

        normalised = source.normalize(raw)
        logger.info("Normalised %d records from %s", len(normalised), name)

        written = source.upsert(normalised)
        logger.info("Upserted %d records from %s", written, name)

    logger.info("Pipeline complete for %d source(s).", len(sources))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_pipeline.py -v
```

Expected: 5 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add ingestion/pipeline.py tests/test_pipeline.py
git commit -m "feat: add watermark-aware run() to ingestion pipeline"
```

---

## Task 3: Add APScheduler + ingest endpoints to `api/main.py`

**Files:**
- Modify: `api/main.py`
- Test: `tests/test_ingest_endpoints.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ingest_endpoints.py`:

```python
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


def test_ingest_strava_returns_ok():
    with patch("ingestion.pipeline.run", return_value={"records_fetched": 3, "records_inserted": 2, "records_skipped": 1}):
        with TestClient(app) as client:
            response = client.post("/ingest/strava")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["source"] == "strava"
    assert data["records_inserted"] == 2


def test_ingest_whoop_returns_ok():
    with patch("ingestion.pipeline.run", return_value={"records_fetched": 1, "records_inserted": 1, "records_skipped": 0}):
        with TestClient(app) as client:
            response = client.post("/ingest/whoop")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["source"] == "whoop"
    assert data["records_inserted"] == 1


def test_health_still_returns_ok():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_ingest_endpoints.py -v
```

Expected: `404 Not Found` for the ingest endpoints

- [ ] **Step 3: Rewrite `api/main.py`**

Replace the entire file:

```python
"""FastAPI application: health check, chat endpoint, and on-demand ingestion triggers."""

from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import agent.agent as agent_module
from ingestion import pipeline

_scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _scheduler.add_job(
        lambda: pipeline.run("whoop"),
        CronTrigger(hour=9, minute=0, timezone="Europe/Paris"),
        id="whoop_daily",
        replace_existing=True,
    )
    _scheduler.add_job(
        lambda: pipeline.run("strava"),
        CronTrigger(hour=20, minute=0, timezone="Europe/Paris"),
        id="strava_daily",
        replace_existing=True,
    )
    _scheduler.start()
    yield
    _scheduler.shutdown()


app = FastAPI(title="Running Coach AI", lifespan=lifespan)


# --- Request / response schemas -------------------------------------------


class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    response: str


class IngestResponse(BaseModel):
    status: str
    source: str
    records_inserted: int


# --- Routes ---------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe — returns 200 when the service is up."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Run the user query through the agent and return the response."""
    response = agent_module.run(request.query)
    return ChatResponse(response=response)


@app.post("/ingest/whoop", response_model=IngestResponse)
def ingest_whoop() -> IngestResponse:
    """Trigger an immediate Whoop ingestion run."""
    try:
        result = pipeline.run("whoop")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return IngestResponse(status="ok", source="whoop", records_inserted=result["records_inserted"])


@app.post("/ingest/strava", response_model=IngestResponse)
def ingest_strava() -> IngestResponse:
    """Trigger an immediate Strava ingestion run."""
    try:
        result = pipeline.run("strava")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return IngestResponse(status="ok", source="strava", records_inserted=result["records_inserted"])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_ingest_endpoints.py -v
```

Expected: 3 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add api/main.py tests/test_ingest_endpoints.py
git commit -m "feat: add APScheduler and ingest endpoints to FastAPI"
```

---

## Task 4: Add `refresh_data` agent tool to `agent/tools.py`

**Files:**
- Modify: `agent/tools.py`
- Test: `tests/test_refresh_tool.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_refresh_tool.py`:

```python
from unittest.mock import MagicMock, patch

from agent.tools import refresh_data


def _mock_response(source: str, records_inserted: int) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"status": "ok", "source": source, "records_inserted": records_inserted}
    return resp


def test_refresh_whoop_with_new_record():
    with patch("agent.tools.requests.post", return_value=_mock_response("whoop", 1)) as mock_post:
        result = refresh_data.invoke({"source": "whoop"})

    mock_post.assert_called_once()
    assert "Whoop" in result
    assert "1 new record" in result


def test_refresh_strava_already_up_to_date():
    with patch("agent.tools.requests.post", return_value=_mock_response("strava", 0)):
        result = refresh_data.invoke({"source": "strava"})

    assert "Strava" in result
    assert "already up to date" in result


def test_refresh_all_calls_both_sources():
    responses = [_mock_response("whoop", 1), _mock_response("strava", 2)]
    with patch("agent.tools.requests.post", side_effect=responses):
        result = refresh_data.invoke({"source": "all"})

    assert "Whoop" in result
    assert "Strava" in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_refresh_tool.py -v
```

Expected: `ImportError: cannot import name 'refresh_data'`

- [ ] **Step 3: Replace `agent/tools.py`**

```python
"""Tool definitions for the LangChain agent."""

import os

import requests
from langchain_core.tools import tool

_API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


@tool
def refresh_data(source: str) -> str:
    """Fetch the latest data from Whoop and/or Strava and update the database.

    Use this tool when the user asks to refresh data, check if data is fresh,
    or explicitly requests pulling the latest recovery or activity records.

    Args:
        source: Which source to refresh — "whoop", "strava", or "all".

    Returns:
        A plain-English summary of how many records were inserted.
    """
    sources = ["whoop", "strava"] if source == "all" else [source]
    summaries = []

    for s in sources:
        response = requests.post(f"{_API_BASE_URL}/ingest/{s}", timeout=60)
        response.raise_for_status()
        data = response.json()
        n = data["records_inserted"]
        label = s.capitalize()
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

- [ ] **Step 4: Run test to verify it passes**

```bash
poetry run pytest tests/test_refresh_tool.py -v
```

Expected: 3 tests PASSED

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
poetry run pytest -v
```

Expected: all tests PASSED (or pre-existing failures unrelated to this change)

- [ ] **Step 6: Commit**

```bash
git add agent/tools.py tests/test_refresh_tool.py
git commit -m "feat: add refresh_data agent tool"
```

---

## Task 5: Create Streamlit UI with "Refresh All" button

**Files:**
- Modify: `pyproject.toml`
- Create: `ui/__init__.py`
- Create: `ui/app.py`

No automated tests for Streamlit — verified manually by running the app.

- [ ] **Step 1: Add `streamlit` to `pyproject.toml`**

In the `[tool.poetry.dependencies]` section, add:

```toml
streamlit = "^1.35"
```

- [ ] **Step 2: Install the new dependency**

```bash
poetry install
```

Expected: installs streamlit and its dependencies without errors

- [ ] **Step 3: Create `ui/__init__.py`**

Create an empty file at `ui/__init__.py`.

- [ ] **Step 4: Create `ui/app.py`**

```python
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
```

- [ ] **Step 5: Start the FastAPI server in one terminal**

```bash
poetry run uvicorn api.main:app --reload
```

- [ ] **Step 6: Start the Streamlit app in a second terminal**

```bash
poetry run streamlit run ui/app.py
```

Expected: browser opens at `http://localhost:8501`, sidebar shows "Refresh All" button

- [ ] **Step 7: Test the Refresh All button**

Click "Refresh All" in the sidebar. Expected: spinner appears, then `"Synced — N new records."` success message.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml poetry.lock ui/__init__.py ui/app.py
git commit -m "feat: add Streamlit UI with Refresh All button"
```

---

## Final verification

- [ ] **Run the full test suite one last time**

```bash
poetry run pytest -v
```

Expected: all tests pass.
