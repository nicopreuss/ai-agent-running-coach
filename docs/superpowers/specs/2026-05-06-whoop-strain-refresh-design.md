# Whoop Strain Live Refresh — Design Spec

**Date:** 2026-05-06
**Status:** Approved

## Problem

`daily_strain` accumulates throughout the day on the same Whoop cycle. The current ingestion
uses `ON CONFLICT DO NOTHING`, so once a row is inserted the strain is frozen at whatever
value it had at first ingestion. A manual refresh via the UI button never updates it.

There is a second bug: the Whoop API filters cycles by their start time. Today's cycle starts
in the morning (e.g. 6am), but after a successful run the watermark advances past that point
(e.g. 9am). On the next refresh, the API returns no cycles since none started after 9am —
so today's row is not even re-fetched.

Both bugs must be fixed together or the upsert change has no effect.

## Out of scope

- Updating any field other than `daily_strain` on refresh (recovery score, HRV, and sleep
  fields are morning snapshots and are final once set)
- Updating historical rows (past days' strain is final)
- Any schema or ingestion_log changes (the pipeline already writes a fresh log row on every
  successful run)

## Changes

### 1. Watermark floor — `ingestion/pipeline.py`

When constructing the Whoop `start_date` from the watermark, clamp it to
`min(watermark, start_of_today_utc)`. This ensures today's cycle (which started before the
watermark) is always included in the fetch window. Historical behaviour is unchanged: for
backfills (no watermark) `start_date` remains `None`.

```python
from datetime import date, datetime, time, timezone

if watermark:
    today_start = datetime.combine(date.today(), time.min).replace(tzinfo=timezone.utc)
    effective = min(watermark, today_start)
    start_date = effective.strftime("%Y-%m-%dT%H:%M:%S.000Z")
else:
    start_date = None
```

### 2. Conditional upsert — `ingestion/sources/whoop.py`

Replace `on_conflict_do_nothing` with `on_conflict_do_update`, updating only `daily_strain`
from the incoming row, restricted to today's date via a `WHERE` clause.

```python
stmt = (
    insert(WhoopRecoveryDaily)
    .values(records)
    .on_conflict_do_update(
        index_elements=["whoop_cycle_id"],
        set_={"daily_strain": insert(WhoopRecoveryDaily).excluded.daily_strain},
        where=(WhoopRecoveryDaily.date == date.today()),
    )
)
```

When `WHERE date = today` is false (historical rows), PostgreSQL treats the conflict as
DO NOTHING — no data is mutated. When true, only `daily_strain` is overwritten.

## Files touched

| File | Change |
|------|--------|
| `ingestion/pipeline.py` | Clamp Whoop watermark to `min(watermark, start_of_today_utc)` |
| `ingestion/sources/whoop.py` | `on_conflict_do_update` with `daily_strain` + `WHERE date = today` |
| `tests/test_whoop_normalize.py` | Add / update tests for the new upsert behaviour |
| `tests/test_pipeline.py` | Add test for watermark clamping |
