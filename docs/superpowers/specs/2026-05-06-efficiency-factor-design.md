# Efficiency Factor — Design Spec

**Date:** 2026-05-06
**Status:** Approved

## Goal

Add `efficiency_factor` to every Strava run: a single number that measures aerobic efficiency.
Compute it at ingestion time, backfill historical rows, and surface it on the dashboard next
to avg BPM.

## Formula

```
EF = (distance_meters * 60.0 / duration_seconds) / avg_heart_rate
```

Speed is expressed in metres per minute (m/min), which is the TrainingPeaks/Garmin convention.
Typical values for a recreational runner: 0.8–2.0. A 5:00/km run at 150 bpm gives EF ≈ 1.33.

`EF` is `NULL` when any of `avg_heart_rate`, `distance_meters`, or `duration_seconds` is NULL
or when `duration_seconds = 0`.

## Files touched

| File | Change |
|------|--------|
| `db/models.py` | Add `efficiency_factor: Float \| None` column to `StravaActivity` |
| `ingestion/sources/strava.py` | Compute EF in `normalize()` alongside `avg_pace_sec_per_km` |
| `scripts/add_efficiency_factor.py` | Migration: ADD COLUMN + one-time UPDATE backfill |
| `api/dashboard.py` | Add `efficiency_factor` to `LastRunSnapshot` model and SQL query |
| `ui/app.py` | Display EF metric in the Last Run row next to avg BPM |

## Component details

### db/models.py

Add one nullable Float column to `StravaActivity`:

```python
efficiency_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
```

### ingestion/sources/strava.py — normalize()

Compute EF from the raw activity dict before building the record dict.
Guard against NULL and zero to avoid division errors:

```python
avg_hr: float | None = a.get("average_heartrate")
ef = (
    (distance_m * 60.0 / duration_s) / avg_hr
    if (distance_m > 0 and duration_s > 0 and avg_hr)
    else None
)
```

Add `"efficiency_factor": ef` to the returned record dict.

### scripts/add_efficiency_factor.py

One-time idempotent migration — safe to re-run:

1. `ALTER TABLE strava_activities ADD COLUMN IF NOT EXISTS efficiency_factor FLOAT`
2. Backfill existing rows:

```sql
UPDATE strava_activities
SET efficiency_factor = (distance_meters * 60.0 / duration_seconds) / avg_heart_rate
WHERE avg_heart_rate IS NOT NULL
  AND duration_seconds > 0
  AND distance_meters > 0
  AND efficiency_factor IS NULL
```

Run with: `poetry run python -m scripts.add_efficiency_factor`

### api/dashboard.py

Add to `LastRunSnapshot`:
```python
efficiency_factor: float | None
```

Add `efficiency_factor` to the SQL SELECT and pass it through in the constructor.

### ui/app.py

Add a 5th column to the Last Run metrics row. Format as `f"{ef:.2f}"` when present, show
`"N/A"` when NULL. Position: immediately after avg BPM.

## Out of scope

- Recomputing EF for past runs on every subsequent ingest (they are final once inserted;
  the backfill script handles the one-time population)
- Exposing EF through the agent tools (can be added later if needed)
- EF trend chart on the dashboard
