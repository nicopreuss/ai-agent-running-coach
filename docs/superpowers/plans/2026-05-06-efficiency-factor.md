# Efficiency Factor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `efficiency_factor` (aerobic efficiency metric) to every Strava run — compute at ingestion, backfill historical rows, and display it on the dashboard next to avg BPM.

**Architecture:** Four layers in dependency order — ORM column + ingestion computation first, then the one-time migration for historical data, then the API, then the UI. Each layer has its own tests and commit.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0, FastAPI/Pydantic, Streamlit, `unittest.mock`, pytest.

---

## File Map

| Action | Path | Change |
|--------|------|--------|
| Modify | `db/models.py:47` | Add `efficiency_factor` nullable Float column after `perceived_effort` |
| Modify | `ingestion/sources/strava.py:91-126` | Compute EF in `normalize()`, reuse `avg_hr` variable |
| Create | `tests/test_strava_normalize.py` | 3 tests for EF computation |
| Create | `scripts/add_efficiency_factor.py` | ALTER TABLE IF NOT EXISTS + backfill UPDATE |
| Create | `tests/test_add_efficiency_factor.py` | 2 tests for migration |
| Modify | `api/dashboard.py:19-95` | Add `efficiency_factor` field to `LastRunSnapshot` and SQL SELECT |
| Modify | `tests/test_dashboard_endpoint.py` | Update 1 existing test + add 2 new EF tests |
| Modify | `ui/app.py:81-85` | Expand to 5 columns, add EF metric after Avg BPM |

---

## Task 1: ORM column + normalize computation

**Files:**
- Modify: `db/models.py:47`
- Modify: `ingestion/sources/strava.py:91-126`
- Create: `tests/test_strava_normalize.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_strava_normalize.py`:

```python
"""Unit tests for StravaSource.normalize() — efficiency factor computation."""

import pytest


@pytest.fixture(autouse=True)
def strava_env(monkeypatch):
    monkeypatch.setenv("STRAVA_CLIENT_ID", "test-id")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("STRAVA_REFRESH_TOKEN", "test-refresh")
    monkeypatch.setenv("STRAVA_ACCESS_TOKEN", "test-access")


def _make_activity(**kwargs) -> dict:
    """Minimal Strava activity dict with required fields."""
    base = {
        "id": 1,
        "type": "Run",
        "start_date_local": "2024-01-15T08:00:00",
        "distance": 5000.0,
        "moving_time": 1500,
        "average_heartrate": 150.0,
    }
    base.update(kwargs)
    return base


def test_normalize_computes_efficiency_factor():
    """EF = (distance_m * 60 / duration_s) / avg_hr.
    5000m * 60 / 1500s = 200 m/min; 200 / 150 bpm = 1.333...
    """
    from ingestion.sources.strava import StravaSource

    source = StravaSource()
    records = source.normalize([_make_activity()])

    assert len(records) == 1
    assert records[0]["efficiency_factor"] == pytest.approx(200.0 / 150.0, rel=1e-6)


def test_normalize_efficiency_factor_null_when_no_heart_rate():
    """EF is None when average_heartrate is absent."""
    from ingestion.sources.strava import StravaSource

    source = StravaSource()
    records = source.normalize([_make_activity(average_heartrate=None)])

    assert records[0]["efficiency_factor"] is None


def test_normalize_efficiency_factor_null_when_zero_duration():
    """EF is None when moving_time is 0 (avoids division by zero)."""
    from ingestion.sources.strava import StravaSource

    source = StravaSource()
    records = source.normalize([_make_activity(moving_time=0)])

    assert records[0]["efficiency_factor"] is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_strava_normalize.py -v
```

Expected: 3 FAIL — `KeyError: 'efficiency_factor'` (the key is not in the returned dict yet).

- [ ] **Step 3: Add the ORM column to `db/models.py`**

In `db/models.py`, add one line after the `perceived_effort` column (line 47). The block should look like:

```python
    suffer_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    perceived_effort: Mapped[int | None] = mapped_column(Integer, nullable=True)
    efficiency_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 4: Compute EF in `ingestion/sources/strava.py`**

Replace the entire `normalize()` method (lines 91–126):

```python
    def normalize(self, raw: list[dict]) -> list[dict]:
        """Transform raw Strava activity dicts into the activities table schema."""
        records = []
        for a in raw:
            distance_m: float = a.get("distance") or 0
            duration_s: int = a.get("moving_time") or 0
            avg_pace = (duration_s / (distance_m / 1000)) if distance_m > 0 else None

            avg_hr: float | None = a.get("average_heartrate")
            ef = (
                (distance_m * 60.0 / duration_s) / avg_hr
                if (distance_m > 0 and duration_s > 0 and avg_hr)
                else None
            )

            start_local: str = a.get("start_date_local", "")
            activity_date = (
                datetime.fromisoformat(start_local.replace("Z", "")).date()
                if start_local
                else None
            )

            records.append(
                {
                    "id": uuid.uuid4(),
                    "strava_activity_id": a["id"],
                    "date": activity_date,
                    "start_time": a.get("start_date"),
                    "name": a.get("name"),
                    "distance_meters": distance_m,
                    "duration_seconds": duration_s,
                    "elapsed_time_seconds": a.get("elapsed_time"),
                    "avg_pace_sec_per_km": avg_pace,
                    "avg_heart_rate": avg_hr,
                    "max_heart_rate": a.get("max_heartrate"),
                    "avg_cadence": a.get("average_cadence"),
                    "elevation_gain_meters": a.get("total_elevation_gain"),
                    "suffer_score": a.get("suffer_score"),
                    "pr_count": a.get("pr_count", 0),
                    "perceived_effort": a.get("perceived_exertion"),
                    "efficiency_factor": ef,
                }
            )
        return records
```

Note: `avg_hr` replaces the inline `a.get("average_heartrate")` call so the variable is computed once and reused.

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_strava_normalize.py -v
```

Expected: 3 PASS.

- [ ] **Step 6: Run the full test suite**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest --tb=short -q
```

Expected: all existing tests pass.

- [ ] **Step 7: Commit**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && git add db/models.py ingestion/sources/strava.py tests/test_strava_normalize.py && git commit -m "feat: add efficiency_factor column and compute in strava normalize()"
```

---

## Task 2: Migration script

**Files:**
- Create: `scripts/add_efficiency_factor.py`
- Create: `tests/test_add_efficiency_factor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_add_efficiency_factor.py`:

```python
"""Tests for scripts/add_efficiency_factor.py."""

from unittest.mock import MagicMock, patch


def _patch_conn(mock_conn: MagicMock):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=mock_conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return patch("scripts.add_efficiency_factor.get_connection", return_value=ctx)


def test_add_efficiency_factor_executes_alter_and_backfill():
    """Both the ALTER TABLE and the UPDATE backfill must be executed and committed."""
    mock_conn = MagicMock()
    mock_conn.execute.return_value.rowcount = 5

    with _patch_conn(mock_conn):
        from scripts.add_efficiency_factor import add_efficiency_factor
        result = add_efficiency_factor()

    assert mock_conn.execute.call_count == 2
    assert mock_conn.commit.call_count == 2

    first_sql = str(mock_conn.execute.call_args_list[0][0][0])
    assert "ALTER TABLE" in first_sql
    assert "efficiency_factor" in first_sql

    second_sql = str(mock_conn.execute.call_args_list[1][0][0])
    assert "UPDATE" in second_sql
    assert "efficiency_factor" in second_sql
    assert "avg_heart_rate" in second_sql

    assert result == {"updated": 5}


def test_add_efficiency_factor_returns_zero_when_no_rows_to_backfill():
    """Returns {"updated": 0} when no rows need backfilling."""
    mock_conn = MagicMock()
    mock_conn.execute.return_value.rowcount = 0

    with _patch_conn(mock_conn):
        from scripts.add_efficiency_factor import add_efficiency_factor
        result = add_efficiency_factor()

    assert result == {"updated": 0}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_add_efficiency_factor.py -v
```

Expected: 2 FAIL — `ModuleNotFoundError: No module named 'scripts.add_efficiency_factor'`.

- [ ] **Step 3: Implement the migration script**

Create `scripts/add_efficiency_factor.py`:

```python
"""One-time idempotent migration: add efficiency_factor to strava_activities."""

from sqlalchemy import text

from db.client import get_connection


def add_efficiency_factor() -> dict:
    """Add efficiency_factor column and backfill existing rows.

    Safe to re-run: ADD COLUMN IF NOT EXISTS skips the ALTER when the column
    already exists; UPDATE WHERE efficiency_factor IS NULL skips filled rows.
    """
    with get_connection() as conn:
        conn.execute(
            text(
                "ALTER TABLE strava_activities "
                "ADD COLUMN IF NOT EXISTS efficiency_factor FLOAT"
            )
        )
        conn.commit()

        result = conn.execute(
            text(
                """
                UPDATE strava_activities
                SET efficiency_factor = (distance_meters * 60.0 / duration_seconds) / avg_heart_rate
                WHERE avg_heart_rate IS NOT NULL
                  AND duration_seconds > 0
                  AND distance_meters > 0
                  AND efficiency_factor IS NULL
                """
            )
        )
        conn.commit()
        return {"updated": result.rowcount}


def main() -> None:
    result = add_efficiency_factor()
    print(f"Backfilled {result['updated']} rows with efficiency_factor.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_add_efficiency_factor.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Run the full test suite**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && git add scripts/add_efficiency_factor.py tests/test_add_efficiency_factor.py && git commit -m "feat: add efficiency factor migration script with backfill"
```

---

## Task 3: Dashboard API

**Files:**
- Modify: `api/dashboard.py:19-95`
- Modify: `tests/test_dashboard_endpoint.py`

- [ ] **Step 1: Update the existing test and add two new tests**

In `tests/test_dashboard_endpoint.py`:

**Update** `test_get_last_run_snapshot_converts_meters_to_km` — add `"efficiency_factor"` to its data dict and assert on the new field:

```python
def test_get_last_run_snapshot_converts_meters_to_km():
    data = {
        "distance_meters": 8200.0,
        "duration_seconds": 2712,
        "avg_pace_sec_per_km": 330.0,
        "avg_heart_rate": 148.0,
        "efficiency_factor": 1.35,
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
    assert result.efficiency_factor == 1.35
```

**Add** these two new tests at the bottom of the file:

```python
def test_get_last_run_snapshot_includes_ef_when_present():
    data = {
        "distance_meters": 5000.0,
        "duration_seconds": 1500,
        "avg_pace_sec_per_km": 300.0,
        "avg_heart_rate": 150.0,
        "efficiency_factor": 1.33,
        "date": datetime.date(2026, 5, 4),
    }
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = _mock_row(data)

    result = get_last_run_snapshot(conn)

    assert result.efficiency_factor == 1.33


def test_get_last_run_snapshot_ef_is_none_when_null():
    data = {
        "distance_meters": 5000.0,
        "duration_seconds": 1500,
        "avg_pace_sec_per_km": 300.0,
        "avg_heart_rate": 150.0,
        "efficiency_factor": None,
        "date": datetime.date(2026, 5, 4),
    }
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = _mock_row(data)

    result = get_last_run_snapshot(conn)

    assert result.efficiency_factor is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_dashboard_endpoint.py -v
```

Expected: `test_get_last_run_snapshot_converts_meters_to_km` FAIL (field missing on model), `test_get_last_run_snapshot_includes_ef_when_present` FAIL, `test_get_last_run_snapshot_ef_is_none_when_null` FAIL.

- [ ] **Step 3: Implement the API changes**

In `api/dashboard.py`, update `LastRunSnapshot` to add the new nullable field:

```python
class LastRunSnapshot(BaseModel):
    distance_km: float
    duration_seconds: int
    avg_pace_sec_per_km: float
    avg_heart_rate: float
    efficiency_factor: float | None = None
    date: datetime.date
```

Replace `get_last_run_snapshot()` in full:

```python
def get_last_run_snapshot(conn: Connection) -> LastRunSnapshot | None:
    row = (
        conn.execute(
            text(
                """
                SELECT distance_meters, duration_seconds, avg_pace_sec_per_km,
                       avg_heart_rate, efficiency_factor, date
                FROM strava_activities
                WHERE distance_meters IS NOT NULL
                  AND duration_seconds IS NOT NULL
                  AND avg_pace_sec_per_km IS NOT NULL
                  AND avg_heart_rate IS NOT NULL
                ORDER BY date DESC
                LIMIT 1
                """
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return LastRunSnapshot(
        distance_km=round(row["distance_meters"] / 1000, 1),
        duration_seconds=row["duration_seconds"],
        avg_pace_sec_per_km=row["avg_pace_sec_per_km"],
        avg_heart_rate=row["avg_heart_rate"],
        efficiency_factor=row["efficiency_factor"],
        date=row["date"],
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_dashboard_endpoint.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Run the full test suite**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && git add api/dashboard.py tests/test_dashboard_endpoint.py && git commit -m "feat: add efficiency_factor to dashboard API and LastRunSnapshot"
```

---

## Task 4: UI

**Files:**
- Modify: `ui/app.py:81-85`

- [ ] **Step 1: Expand the Last Run row to 5 columns**

In `ui/app.py`, replace lines 81–85 (the 4-column Last Run block):

```python
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Distance", f'{last_run["distance_km"]:.1f} km')
        c2.metric("Duration", _fmt_duration(last_run["duration_seconds"]))
        c3.metric("Avg Pace", _fmt_pace(last_run["avg_pace_sec_per_km"]))
        c4.metric("Avg BPM", f'{last_run["avg_heart_rate"]:.0f}')
```

with:

```python
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Distance", f'{last_run["distance_km"]:.1f} km')
        c2.metric("Duration", _fmt_duration(last_run["duration_seconds"]))
        c3.metric("Avg Pace", _fmt_pace(last_run["avg_pace_sec_per_km"]))
        c4.metric("Avg BPM", f'{last_run["avg_heart_rate"]:.0f}')
        ef = last_run.get("efficiency_factor")
        c5.metric("EF", f"{ef:.2f}" if ef is not None else "N/A")
```

- [ ] **Step 2: Run the full test suite**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && git add ui/app.py && git commit -m "feat: display efficiency_factor on dashboard next to avg BPM"
```

---

## Task 5: Push and raise PR

- [ ] **Step 1: Push the branch**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && git push -u origin feat/efficiency-factor
```

- [ ] **Step 2: Create the PR**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && gh pr create \
  --title "feat: add efficiency factor to strava runs and dashboard" \
  --body "$(cat <<'EOF'
## Summary

- Adds `efficiency_factor` (EF = speed in m/min ÷ avg HR) as a nullable Float column to `strava_activities`
- Computes EF at ingestion time in `StravaSource.normalize()` — NULL when HR, distance, or duration is missing/zero
- Adds `scripts/add_efficiency_factor.py`: idempotent migration that ALTER TABLE adds the column and backfills historical rows via a single SQL UPDATE
- Surfaces EF on the dashboard as a 5th metric in the Last Run row, formatted to 2 decimal places ("N/A" when NULL)

## Test plan

- [ ] All new and existing tests pass (`poetry run pytest`)
- [ ] Run `poetry run python -m scripts.add_efficiency_factor` and verify historical rows are backfilled
- [ ] Check the dashboard — EF appears next to Avg BPM on the Last Run row

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
