# Whoop Ingestion Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the full Whoop ingestion pipeline — `fetch()`, `normalize()`, `upsert()` on `WhoopSource` — to populate the `recovery_daily` table in Supabase with daily recovery data.

**Architecture:** Paginate three Whoop v2 endpoints (`/cycle`, `/recovery`, `/activity/sleep`) independently into dicts keyed by `cycle_id`, filter out naps, then join into `{"cycle": ..., "recovery": ..., "sleep": ...}` structs. `normalize()` maps those nested keys to the `RecoveryDaily` ORM schema. `upsert()` deduplicates on `whoop_cycle_id`.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0, psycopg2-binary, requests, Supabase/Postgres, Poetry

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `db/models.py` | Modify | Add `RecoveryDaily` ORM model |
| `ingestion/sources/whoop.py` | Modify | Add `_paginate()`, implement `fetch()`, `normalize()`, `upsert()` |
| `tests/test_whoop_normalize.py` | Create | Unit tests for `normalize()` with fixture data |
| `scripts/smoke_test_whoop_ingest.py` | Create | Manual e2e smoke test — no DB mocking |

---

## Task 1: Add `RecoveryDaily` ORM model to `db/models.py`

**Files:**
- Modify: `db/models.py`

- [ ] **Step 1: Add the model**

Open `db/models.py`. After the `StravaActivity` class, add:

```python
class RecoveryDaily(Base):
    __tablename__ = "recovery_daily"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    whoop_cycle_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    recovery_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hrv_rmssd_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    resting_heart_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_performance_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_efficiency_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    swo_deep_sleep_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rem_sleep_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    light_sleep_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sleep_consistency_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_strain: Mapped[float | None] = mapped_column(Float, nullable=True)
    skin_temp_celsius: Mapped[float | None] = mapped_column(Float, nullable=True)
    spo2_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

All existing imports in `db/models.py` already cover the types needed (`BigInteger`, `Date`, `DateTime`, `Float`, `Integer`, `UUID`, `func`, `Mapped`, `mapped_column`). No new imports required.

- [ ] **Step 2: Verify the model is picked up by SQLAlchemy**

```bash
cd <project-root>
poetry run python -c "from db.models import RecoveryDaily; print(RecoveryDaily.__tablename__)"
```

Expected output:
```
recovery_daily
```

- [ ] **Step 3: Create the table in Supabase**

```bash
poetry run python -m scripts.create_tables
```

Expected output:
```
Connecting to: postgresql://postgres.xxx:***@db.xxx.supabase.co:5432/postgres
Tables created (or already exist): ['strava_activities', 'recovery_daily']
```

- [ ] **Step 4: Commit**

```bash
git add db/models.py
git commit -m "Add RecoveryDaily ORM model for Whoop recovery_daily table"
```

---

## Task 2: Add `_paginate()` to `WhoopSource`

**Files:**
- Modify: `ingestion/sources/whoop.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_whoop_normalize.py`:

```python
"""Unit tests for WhoopSource._paginate() and normalize()."""

from unittest.mock import MagicMock, patch
import os

import pytest


@pytest.fixture(autouse=True)
def whoop_env(monkeypatch):
    monkeypatch.setenv("WHOOP_CLIENT_ID", "test-id")
    monkeypatch.setenv("WHOOP_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("WHOOP_REFRESH_TOKEN", "test-refresh")
    monkeypatch.setenv("WHOOP_ACCESS_TOKEN", "test-access")


def test_paginate_single_page():
    from ingestion.sources.whoop import WhoopSource

    source = WhoopSource()

    page = {"records": [{"id": 1}, {"id": 2}], "next_token": None}
    source._get = MagicMock(return_value=page)

    result = source._paginate("/cycle")

    assert result == [{"id": 1}, {"id": 2}]
    source._get.assert_called_once_with("/cycle", {"limit": 25})


def test_paginate_multiple_pages():
    from ingestion.sources.whoop import WhoopSource

    source = WhoopSource()

    page1 = {"records": [{"id": 1}], "next_token": "tok123"}
    page2 = {"records": [{"id": 2}], "next_token": None}
    source._get = MagicMock(side_effect=[page1, page2])

    result = source._paginate("/cycle")

    assert result == [{"id": 1}, {"id": 2}]
    assert source._get.call_count == 2
    source._get.assert_called_with("/cycle", {"limit": 25, "nextToken": "tok123"})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_whoop_normalize.py::test_paginate_single_page -v
```

Expected: `FAILED` — `WhoopSource` has no `_paginate` method yet.

- [ ] **Step 3: Implement `_paginate()` in `ingestion/sources/whoop.py`**

Add this method to `WhoopSource` after `_get()` and before `fetch()`:

```python
def _paginate(self, path: str, params: dict | None = None) -> list[dict]:
    """Fetch all pages from a cursor-paginated Whoop endpoint."""
    results = []
    next_token = None
    while True:
        page_params = {**(params or {}), "limit": 25}
        if next_token:
            page_params["nextToken"] = next_token
        data = self._get(path, page_params)
        results.extend(data.get("records", []))
        next_token = data.get("next_token")
        if not next_token:
            break
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_whoop_normalize.py -v
```

Expected:
```
test_whoop_normalize.py::test_paginate_single_page PASSED
test_whoop_normalize.py::test_paginate_multiple_pages PASSED
```

- [ ] **Step 5: Commit**

```bash
git add ingestion/sources/whoop.py tests/test_whoop_normalize.py
git commit -m "Add _paginate() to WhoopSource with unit tests"
```

---

## Task 3: Implement `fetch()`

**Files:**
- Modify: `ingestion/sources/whoop.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_whoop_normalize.py`:

```python
def test_fetch_joins_cycle_recovery_sleep():
    from ingestion.sources.whoop import WhoopSource

    source = WhoopSource()

    cycles = [{"id": 42, "start": "2024-01-15T06:00:00Z", "score": {"strain": 8.5}}]
    recoveries = [{"cycle_id": 42, "score": {"recovery_score": 85.0, "hrv_rmssd_milli": 72.3}}]
    sleeps = [{"cycle_id": 42, "nap": False, "score": {"sleep_performance_percentage": 90.0}}]

    def fake_paginate(path, params=None):
        if path == "/cycle":
            return cycles
        if path == "/recovery":
            return recoveries
        if path == "/activity/sleep":
            return sleeps
        return []

    source._paginate = MagicMock(side_effect=fake_paginate)

    result = source.fetch()

    assert len(result) == 1
    assert result[0]["cycle"]["id"] == 42
    assert result[0]["recovery"]["score"]["recovery_score"] == 85.0
    assert result[0]["sleep"]["score"]["sleep_performance_percentage"] == 90.0


def test_fetch_filters_naps():
    from ingestion.sources.whoop import WhoopSource

    source = WhoopSource()

    cycles = [{"id": 42, "start": "2024-01-15T06:00:00Z", "score": {}}]
    recoveries = [{"cycle_id": 42, "score": {}}]
    sleeps = [
        {"cycle_id": 42, "nap": False, "score": {}},
        {"cycle_id": 42, "nap": True, "score": {}},  # this nap must be excluded
    ]

    def fake_paginate(path, params=None):
        if path == "/cycle": return cycles
        if path == "/recovery": return recoveries
        if path == "/activity/sleep": return sleeps
        return []

    source._paginate = MagicMock(side_effect=fake_paginate)
    result = source.fetch()

    # nap filtered — sleep dict should be the non-nap record
    assert result[0]["sleep"].get("nap") is False


def test_fetch_skips_cycle_with_no_recovery():
    from ingestion.sources.whoop import WhoopSource

    source = WhoopSource()

    cycles = [
        {"id": 42, "start": "2024-01-15T06:00:00Z", "score": {}},
        {"id": 99, "start": "2024-01-16T06:00:00Z", "score": {}},  # no recovery
    ]
    recoveries = [{"cycle_id": 42, "score": {}}]

    def fake_paginate(path, params=None):
        if path == "/cycle": return cycles
        if path == "/recovery": return recoveries
        if path == "/activity/sleep": return []
        return []

    source._paginate = MagicMock(side_effect=fake_paginate)
    result = source.fetch()

    assert len(result) == 1
    assert result[0]["cycle"]["id"] == 42
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_whoop_normalize.py::test_fetch_joins_cycle_recovery_sleep -v
```

Expected: `FAILED` — `fetch()` raises `NotImplementedError`.

- [ ] **Step 3: Implement `fetch()` in `ingestion/sources/whoop.py`**

Replace the `fetch()` stub:

```python
def fetch(self) -> list[dict]:
    """Fetch all daily records from Whoop, joining cycle + recovery + sleep data."""
    params = {"start": self._start_date} if self._start_date else {}

    cycles     = {c["id"]: c for c in self._paginate("/cycle", params)}
    recoveries = {r["cycle_id"]: r for r in self._paginate("/recovery", params)}
    sleeps     = {
        s["cycle_id"]: s
        for s in self._paginate("/activity/sleep", params)
        if not s.get("nap")
    }

    return [
        {"cycle": cycles[cid], "recovery": recoveries[cid], "sleep": sleeps.get(cid, {})}
        for cid in recoveries
        if cid in cycles
    ]
```

- [ ] **Step 4: Run all tests**

```bash
poetry run pytest tests/test_whoop_normalize.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ingestion/sources/whoop.py tests/test_whoop_normalize.py
git commit -m "Implement WhoopSource.fetch() with cycle/recovery/sleep join"
```

---

## Task 4: Implement `normalize()`

**Files:**
- Modify: `ingestion/sources/whoop.py`
- Also add import: `from datetime import date, datetime` at the top

- [ ] **Step 1: Write the failing test**

Add to `tests/test_whoop_normalize.py`:

```python
def test_normalize_maps_all_fields():
    from ingestion.sources.whoop import WhoopSource
    from datetime import date

    source = WhoopSource()

    raw = [{
        "cycle": {
            "id": 42,
            "start": "2024-01-15T06:00:00Z",
            "score": {"strain": 8.5},
        },
        "recovery": {
            "cycle_id": 42,
            "score": {
                "recovery_score": 85.0,
                "hrv_rmssd_milli": 72.3,
                "resting_heart_rate": 48.0,
                "skin_temp_celsius": 36.1,
                "spo2_percentage": 98.0,
            },
        },
        "sleep": {
            "cycle_id": 42,
            "score": {
                "sleep_performance_percentage": 90.0,
                "sleep_efficiency_percentage": 88.0,
                "sleep_consistency_percentage": 75.0,
                "stage_summary": {
                    "total_in_bed_time_milli": 28800000,
                    "slow_wave_sleep_duration_milli": 5400000,
                    "rem_sleep_duration_milli": 7200000,
                    "light_sleep_duration_milli": 10800000,
                },
            },
        },
    }]

    records = source.normalize(raw)

    assert len(records) == 1
    r = records[0]
    assert r["date"] == date(2024, 1, 15)
    assert r["whoop_cycle_id"] == 42
    assert r["recovery_score"] == 85.0
    assert r["hrv_rmssd_ms"] == 72.3
    assert r["resting_heart_rate"] == 48.0
    assert r["daily_strain"] == 8.5
    assert r["sleep_performance_pct"] == 90.0
    assert r["sleep_efficiency_pct"] == 88.0
    assert r["sleep_consistency_pct"] == 75.0
    assert r["sleep_duration_ms"] == 28800000
    assert r["swo_deep_sleep_ms"] == 5400000
    assert r["rem_sleep_ms"] == 7200000
    assert r["light_sleep_ms"] == 10800000
    assert r["skin_temp_celsius"] == 36.1
    assert r["spo2_percentage"] == 98.0


def test_normalize_handles_missing_sleep():
    from ingestion.sources.whoop import WhoopSource

    source = WhoopSource()

    raw = [{
        "cycle": {"id": 99, "start": "2024-01-16T06:00:00Z", "score": {"strain": 5.0}},
        "recovery": {"cycle_id": 99, "score": {"recovery_score": 70.0, "hrv_rmssd_milli": 60.0, "resting_heart_rate": 52.0}},
        "sleep": {},
    }]

    records = source.normalize(raw)

    assert len(records) == 1
    assert records[0]["sleep_performance_pct"] is None
    assert records[0]["sleep_duration_ms"] is None
    assert records[0]["recovery_score"] == 70.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_whoop_normalize.py::test_normalize_maps_all_fields -v
```

Expected: `FAILED` — `normalize()` raises `NotImplementedError`.

- [ ] **Step 3: Implement `normalize()` in `ingestion/sources/whoop.py`**

Add `from datetime import datetime` to imports at the top of the file. Then replace the `normalize()` stub:

```python
def normalize(self, raw: list[dict]) -> list[dict]:
    """Map merged Whoop dicts to the recovery_daily table schema."""
    records = []
    for r in raw:
        cycle          = r["cycle"]
        recovery       = r["recovery"]
        sleep          = r.get("sleep", {})
        cycle_score    = cycle.get("score") or {}
        recovery_score = recovery.get("score") or {}
        sleep_score    = sleep.get("score") or {}
        stages         = sleep_score.get("stage_summary") or {}

        start = cycle.get("start", "")
        activity_date = (
            datetime.fromisoformat(start.replace("Z", "")).date()
            if start else None
        )

        records.append({
            "date": activity_date,
            "whoop_cycle_id": cycle["id"],
            "recovery_score": recovery_score.get("recovery_score"),
            "hrv_rmssd_ms": recovery_score.get("hrv_rmssd_milli"),
            "resting_heart_rate": recovery_score.get("resting_heart_rate"),
            "sleep_performance_pct": sleep_score.get("sleep_performance_percentage"),
            "sleep_efficiency_pct": sleep_score.get("sleep_efficiency_percentage"),
            "sleep_consistency_pct": sleep_score.get("sleep_consistency_percentage"),
            "sleep_duration_ms": stages.get("total_in_bed_time_milli"),
            "swo_deep_sleep_ms": stages.get("slow_wave_sleep_duration_milli"),
            "rem_sleep_ms": stages.get("rem_sleep_duration_milli"),
            "light_sleep_ms": stages.get("light_sleep_duration_milli"),
            "daily_strain": cycle_score.get("strain"),
            "skin_temp_celsius": recovery_score.get("skin_temp_celsius"),
            "spo2_percentage": recovery_score.get("spo2_percentage"),
        })
    return records
```

- [ ] **Step 4: Run all tests**

```bash
poetry run pytest tests/test_whoop_normalize.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ingestion/sources/whoop.py tests/test_whoop_normalize.py
git commit -m "Implement WhoopSource.normalize() with unit tests"
```

---

## Task 5: Implement `upsert()`

**Files:**
- Modify: `ingestion/sources/whoop.py`

- [ ] **Step 1: Add missing imports to `ingestion/sources/whoop.py`**

At the top of the file, add:

```python
from sqlalchemy.dialects.postgresql import insert

from db.client import get_connection
from db.models import RecoveryDaily
```

- [ ] **Step 2: Replace the `upsert()` stub**

```python
def upsert(self, records: list[dict]) -> int:
    """Insert recovery records, skipping any that already exist (dedup on whoop_cycle_id)."""
    if not records:
        return 0

    with get_connection() as conn:
        stmt = (
            insert(RecoveryDaily)
            .values(records)
            .on_conflict_do_nothing(index_elements=["whoop_cycle_id"])
        )
        result = conn.execute(stmt)
        conn.commit()
        return result.rowcount
```

- [ ] **Step 3: Verify imports resolve**

```bash
poetry run python -c "from ingestion.sources.whoop import WhoopSource; print('OK')"
```

Expected:
```
OK
```

- [ ] **Step 4: Commit**

```bash
git add ingestion/sources/whoop.py
git commit -m "Implement WhoopSource.upsert() — dedup on whoop_cycle_id"
```

---

## Task 6: Create and run the e2e smoke test

**Files:**
- Create: `scripts/smoke_test_whoop_ingest.py`

- [ ] **Step 1: Create the smoke test**

```python
"""Smoke test: full Whoop ingest pipeline — fetch → normalize → upsert → verify in Supabase."""

from sqlalchemy import text

from db.client import get_connection
from ingestion.sources.whoop import WhoopSource


def main() -> None:
    # 1. Count existing rows before ingest
    with get_connection() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM recovery_daily")).scalar()
    print(f"Recovery rows in DB before ingest: {before}")

    # 2. Run pipeline
    source = WhoopSource()

    print("\nFetching from Whoop...")
    raw = source.fetch()
    print(f"  Fetched {len(raw)} raw daily records")

    records = source.normalize(raw)
    print(f"  Normalised {len(records)} records")

    inserted = source.upsert(records)
    skipped = len(records) - inserted
    print(f"  Inserted {inserted} new records  ({skipped} already existed, skipped)")

    # 3. Query DB to confirm rows are there
    with get_connection() as conn:
        after = conn.execute(text("SELECT COUNT(*) FROM recovery_daily")).scalar()
        sample = conn.execute(
            text(
                "SELECT date, recovery_score, hrv_rmssd_ms, resting_heart_rate, sleep_duration_ms "
                "FROM recovery_daily ORDER BY date DESC LIMIT 5"
            )
        ).fetchall()

    print(f"\nRecovery rows in DB after ingest: {after}")
    print("\nMost recent 5 days:")
    for row in sample:
        sleep_h = f"{(row.sleep_duration_ms or 0) / 3_600_000:.1f}h"
        hr = f"HRV={row.hrv_rmssd_ms:.1f}ms" if row.hrv_rmssd_ms else "HRV=n/a"
        print(
            f"  {row.date}  recovery={row.recovery_score or 'n/a':>5}%  "
            f"{hr}  RHR={row.resting_heart_rate or 'n/a'}bpm  sleep={sleep_h}"
        )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the smoke test**

```bash
poetry run python -m scripts.smoke_test_whoop_ingest
```

Expected output (numbers will vary):
```
Recovery rows in DB before ingest: 0

Fetching from Whoop...
  Fetched 312 raw daily records
  Normalised 312 records
  Inserted 312 new records  (0 already existed, skipped)

Recovery rows in DB after ingest: 312

Most recent 5 days:
  2024-01-15  recovery= 98.0%  HRV=88.0ms  RHR=45.0bpm  sleep=7.8h
  ...
```

Re-running should show `Inserted 0 new records  (312 already existed, skipped)`.

- [ ] **Step 3: Verify in Supabase Table Editor**

Open Supabase → Table Editor → `recovery_daily`. Confirm rows are present with correct dates, recovery scores, HRV, and sleep durations.

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke_test_whoop_ingest.py
git commit -m "Add Whoop e2e smoke test script"
```

---

## Task 7: Final push

- [ ] **Push all commits to GitHub**

```bash
git push
```

Expected: all commits from Tasks 1–6 pushed to `main`.
