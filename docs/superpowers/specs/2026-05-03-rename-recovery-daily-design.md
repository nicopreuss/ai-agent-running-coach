# Rename `recovery_daily` → `whoop_recovery_daily` — Design Spec

**Date:** 2026-05-03
**Status:** Approved

---

## Context

The database has two ingestion tables: `strava_activities` (source-prefixed) and `recovery_daily`
(not source-prefixed). Renaming `recovery_daily` to `whoop_recovery_daily` makes the data source
explicit and keeps naming consistent across the schema.

---

## Database Change

Run once in the Supabase SQL Editor **before** deploying code changes:

```sql
ALTER TABLE recovery_daily RENAME TO whoop_recovery_daily;
```

This is instant, preserves all 1,073 existing rows, and carries over the primary key on `date`
and the unique constraint on `whoop_cycle_id`.

---

## Code Changes

### `db/models.py`

- Rename class `RecoveryDaily` → `WhoopRecoveryDaily`
- Change `__tablename__ = "recovery_daily"` → `__tablename__ = "whoop_recovery_daily"`

### `ingestion/sources/whoop.py`

- Import: `from db.models import RecoveryDaily` → `from db.models import WhoopRecoveryDaily`
- Usage in `upsert()`: `insert(RecoveryDaily)` → `insert(WhoopRecoveryDaily)`
- Docstring in `normalize()`: update table name reference

### `scripts/smoke_test_whoop_ingest.py`

- Raw SQL string: `"SELECT COUNT(*) FROM recovery_daily"` → `"SELECT COUNT(*) FROM whoop_recovery_daily"`
- Raw SQL string: `"FROM recovery_daily ORDER BY date DESC LIMIT 5"` → `"FROM whoop_recovery_daily ORDER BY date DESC LIMIT 5"`

### `CLAUDE.md`

- Schema section heading: `### \`recovery_daily\`` → `### \`whoop_recovery_daily\``
- FK reference in `activities` table: `FK → recovery_daily.date` → `FK → whoop_recovery_daily.date`
- Agent tool description: `recovery_daily` → `whoop_recovery_daily`

---

## Files Not Changed

- `tests/test_whoop_normalize.py` — unit tests mock `_paginate` and `_get`; no ORM class or table name references. No changes needed.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` — historical artifacts, not active code.

---

## Verification

| Step | Command | Expected outcome |
|---|---|---|
| Unit tests | `poetry run pytest tests/test_whoop_normalize.py -v` | 7 passed |
| Smoke test | `poetry run python -m scripts.smoke_test_whoop_ingest` | `Inserted 0 new records (1073 already existed, skipped)` |

---

## Ordering

1. User runs `ALTER TABLE` in Supabase SQL Editor
2. Code changes in a single commit
3. Unit tests + smoke test pass
4. Push to GitHub
