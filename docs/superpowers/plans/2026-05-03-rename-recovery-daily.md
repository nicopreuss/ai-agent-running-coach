# Rename recovery_daily → whoop_recovery_daily Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the `recovery_daily` Postgres table and Python ORM class to `whoop_recovery_daily` / `WhoopRecoveryDaily` for source-naming consistency with `strava_activities`.

**Architecture:** One manual Supabase SQL step renames the live table (no data loss), then four code files are updated in-place and committed together in a single commit. The existing unit tests require no changes — they mock all DB interactions.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0, Supabase/Postgres, Poetry

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| Supabase SQL Editor | Manual step | Rename live table without touching data |
| `db/models.py` | Modify | Rename ORM class and `__tablename__` string |
| `ingestion/sources/whoop.py` | Modify | Update import and usage of renamed class |
| `scripts/smoke_test_whoop_ingest.py` | Modify | Update raw SQL table name references |
| `CLAUDE.md` | Modify | Update schema docs and agent tool description |

---

## Task 1: Rename the table in Supabase (manual)

**This is a manual step you perform in the Supabase dashboard — no code to write.**

- [ ] **Step 1: Open the Supabase SQL Editor**

Go to your Supabase project → **SQL Editor** → **New query**.

- [ ] **Step 2: Run the rename**

Paste and execute:

```sql
ALTER TABLE recovery_daily RENAME TO whoop_recovery_daily;
```

Expected: the query returns with no error. The table now appears as `whoop_recovery_daily` in the Table Editor. All 1,073 rows, the `date` primary key, and the `whoop_cycle_id` unique constraint are preserved automatically.

- [ ] **Step 3: Verify in Table Editor**

Open **Table Editor** → confirm `whoop_recovery_daily` is listed and `recovery_daily` is gone.

---

## Task 2: Update `db/models.py`

**Files:**
- Modify: `db/models.py`

- [ ] **Step 1: Rename the class and tablename**

In `db/models.py`, replace the class definition header (lines 51–52):

```python
class WhoopRecoveryDaily(Base):
    __tablename__ = "whoop_recovery_daily"
```

The full updated class (everything else stays the same):

```python
class WhoopRecoveryDaily(Base):
    __tablename__ = "whoop_recovery_daily"

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

- [ ] **Step 2: Verify the import resolves**

```bash
poetry run python -c "from db.models import WhoopRecoveryDaily; print(WhoopRecoveryDaily.__tablename__)"
```

Expected output:
```
whoop_recovery_daily
```

---

## Task 3: Update `ingestion/sources/whoop.py`

**Files:**
- Modify: `ingestion/sources/whoop.py`

- [ ] **Step 1: Update the import**

Replace line 12:

```python
from db.models import WhoopRecoveryDaily
```

- [ ] **Step 2: Update the upsert() method**

In `upsert()`, replace `insert(RecoveryDaily)` with `insert(WhoopRecoveryDaily)`:

```python
    def upsert(self, records: list[dict]) -> int:
        """Insert recovery records, skipping any that already exist (dedup on whoop_cycle_id)."""
        if not records:
            return 0

        with get_connection() as conn:
            stmt = (
                insert(WhoopRecoveryDaily)
                .values(records)
                .on_conflict_do_nothing(index_elements=["whoop_cycle_id"])
            )
            result = conn.execute(stmt)
            conn.commit()
            return result.rowcount
```

- [ ] **Step 3: Update the normalize() docstring**

Replace the docstring on line 113:

```python
    def normalize(self, raw: list[dict]) -> list[dict]:
        """Map merged Whoop dicts to the whoop_recovery_daily table schema."""
```

- [ ] **Step 4: Verify the import resolves**

```bash
poetry run python -c "from ingestion.sources.whoop import WhoopSource; print('OK')"
```

Expected output:
```
OK
```

---

## Task 4: Update `scripts/smoke_test_whoop_ingest.py`

**Files:**
- Modify: `scripts/smoke_test_whoop_ingest.py`

- [ ] **Step 1: Update the two raw SQL strings**

Replace the `main()` function body with the updated SQL references:

```python
def main() -> None:
    # 1. Count existing rows before ingest
    with get_connection() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM whoop_recovery_daily")).scalar()
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
        after = conn.execute(text("SELECT COUNT(*) FROM whoop_recovery_daily")).scalar()
        sample = conn.execute(
            text(
                "SELECT date, recovery_score, hrv_rmssd_ms, resting_heart_rate, sleep_duration_ms "
                "FROM whoop_recovery_daily ORDER BY date DESC LIMIT 5"
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
```

---

## Task 5: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Rename the schema section heading**

Find and replace (line 74):

```markdown
### `whoop_recovery_daily`
```

- [ ] **Step 2: Update the FK reference in the `activities` table**

Find and replace (line 104):

```markdown
| date | DATE | FK → whoop_recovery_daily.date |
```

- [ ] **Step 3: Update the agent tool description**

Find and replace (line 211):

```markdown
Joins `activities` and `whoop_recovery_daily` on `date` to surface correlations.
```

---

## Task 6: Verify, commit, and push

- [ ] **Step 1: Run the unit tests**

```bash
poetry run pytest tests/test_whoop_normalize.py -v
```

Expected output:
```
tests/test_whoop_normalize.py::test_paginate_single_page PASSED
tests/test_whoop_normalize.py::test_paginate_multiple_pages PASSED
tests/test_whoop_normalize.py::test_fetch_joins_cycle_recovery_sleep PASSED
tests/test_whoop_normalize.py::test_fetch_filters_naps PASSED
tests/test_whoop_normalize.py::test_fetch_skips_cycle_with_no_recovery PASSED
tests/test_whoop_normalize.py::test_normalize_maps_all_fields PASSED
tests/test_whoop_normalize.py::test_normalize_handles_missing_sleep PASSED
7 passed
```

- [ ] **Step 2: Run ruff to confirm no lint errors**

```bash
poetry run ruff check .
```

Expected output:
```
All checks passed!
```

- [ ] **Step 3: Run the smoke test**

```bash
poetry run python -m scripts.smoke_test_whoop_ingest
```

Expected output (data preserved from ALTER TABLE rename — no re-ingest needed):
```
Recovery rows in DB before ingest: 1073

Fetching from Whoop...
  Fetched 1157 raw daily records
  Normalised 1073 records
  Inserted 0 new records  (1073 already existed, skipped)

Recovery rows in DB after ingest: 1073

Most recent 5 days:
  2026-05-02  recovery= ...%  HRV=...ms  RHR=...bpm  sleep=...h
  ...
```

- [ ] **Step 4: Commit all changes**

```bash
git add db/models.py ingestion/sources/whoop.py scripts/smoke_test_whoop_ingest.py CLAUDE.md
git commit -m "Rename recovery_daily to whoop_recovery_daily for source naming consistency"
```

- [ ] **Step 5: Push**

```bash
git push
```

Expected:
```
To github.com:nicopreuss/ai-agent-running-coach.git
   <old-sha>..<new-sha>  main -> main
```
