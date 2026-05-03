# Whoop Ingestion Pipeline — Design Spec

**Date:** 2026-05-03
**Status:** Approved

---

## Context

Whoop API connection is working (`WhoopSource` with token management and `_get()` helper). The
`fetch()`, `normalize()`, and `upsert()` methods are stubs. This spec covers implementing the
full pipeline to populate the `recovery_daily` table — one row per calendar day, representing
the athlete's morning health snapshot from Whoop.

---

## Architecture

Two files modified, one new:

| File | Change |
|---|---|
| `db/models.py` | Add `RecoveryDaily` ORM model |
| `ingestion/sources/whoop.py` | Implement `_paginate()`, `fetch()`, `normalize()`, `upsert()` |
| `scripts/smoke_test_whoop_ingest.py` | New — full e2e smoke test |

After implementation, run `scripts/create_tables.py` to create `recovery_daily` in Supabase.

---

## RecoveryDaily ORM Model

Added to `db/models.py`:

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

- `date` is the primary key — one row per calendar day
- `whoop_cycle_id` has a unique constraint — used as the upsert dedup key
- All health fields are nullable — Whoop 4.0+ fields (`skin_temp_celsius`, `spo2_percentage`) are not available on older hardware

---

## Data Flow

```
_paginate("/cycle")           → cycles       {cycle_id → cycle_dict}
_paginate("/recovery")        → recoveries   {cycle_id → recovery_dict}
_paginate("/activity/sleep")  → sleeps       {cycle_id → sleep_dict}  # naps filtered out

fetch() returns:
[
  {"cycle": cycle_dict, "recovery": recovery_dict, "sleep": sleep_dict or {}}
  for cycle_id in recoveries
  if cycle_id in cycles
]
```

Recovery is the anchor — cycles with no recovery record (e.g. device uncharged) are skipped.
Sleep data is merged in where available; missing sleep fields normalize to `None`.

---

## `_paginate()` Helper

Private method on `WhoopSource`, handles the `next_token` cursor loop:

```python
def _paginate(self, path: str, params: dict | None = None) -> list[dict]:
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

---

## `fetch()`

```python
def fetch(self) -> list[dict]:
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

`start_date` filtering uses Whoop's server-side `start` param — no unnecessary pages fetched.
Naps are filtered out at the `sleeps` dict construction step.

---

## `normalize()`

```python
def normalize(self, raw: list[dict]) -> list[dict]:
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

Each data source accessed through its own key — no key collision between cycle/recovery/sleep `score` fields.

---

## `upsert()`

```python
def upsert(self, records: list[dict]) -> int:
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

Idempotent — safe to re-run. Deduplicates on `whoop_cycle_id`.

---

## Smoke Test (`scripts/smoke_test_whoop_ingest.py`)

```
1. Count rows in recovery_daily before ingest
2. WhoopSource().fetch() → normalize() → upsert()
3. Count rows after
4. Print 5 most recent rows: date | recovery_score | hrv | rhr | sleep_hours
```

---

## Verification Steps

| Step | Command | Expected outcome |
|---|---|---|
| Create table | `poetry run python -m scripts.create_tables` | Prints `['strava_activities', 'recovery_daily']` |
| Full ingest | `poetry run python -m scripts.smoke_test_whoop_ingest` | Rows inserted; re-run shows skipped=total |
| Visual check | Supabase Table Editor → `recovery_daily` | Rows with dates, recovery scores, HRV, sleep stages |
