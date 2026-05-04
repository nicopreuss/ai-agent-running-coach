# Dashboard Metrics Panel — Design Spec

## Goal

Replace the "Charts will appear here" placeholder in the Streamlit dashboard with a live
three-row metrics panel showing today's Whoop snapshot, the latest Strava run, and the
next planned Runna session.

---

## Layout

Three stacked rows, each using large-number metric style (matching the approved mockup):

**Row 1 — Whoop (today)**
- Recovery score (colour-coded, see below)
- Sleep performance %
- Daily strain

**Row 2 — Last Run**
- Distance (km)
- Duration (mm:ss)
- Average pace (min:sec /km)
- Average heart rate (bpm)
- Date shown as a subheading (e.g. "Mon 4 May")

**Row 3 — Next Session**
- Session title (from `google_calendar_runna_sessions`)
- Session date
- Days until session: "Today" if date == today, "Tomorrow" if 1 day away, "In N days" otherwise

If any section has no data in the DB, it shows a muted "No data yet" message — no crash.

---

## Recovery Score Colour Coding

`st.metric()` does not support custom colours. The recovery score is rendered via
`st.markdown()` with inline HTML:

| Score | Colour | Hex |
|---|---|---|
| ≥ 70% | Green | `#4ade80` |
| 40–69% | Yellow | `#facc15` |
| < 40% | Red | `#f87171` |

All other metrics use standard `st.metric()`.

---

## Architecture

### New file: `api/dashboard.py`

Three query functions + one Pydantic response model.

**`WhoopSnapshot`**
```python
class WhoopSnapshot(BaseModel):
    recovery_score: float
    sleep_performance_pct: float
    daily_strain: float
    date: datetime.date
```

**`LastRunSnapshot`**
```python
class LastRunSnapshot(BaseModel):
    distance_km: float          # distance_meters / 1000
    duration_seconds: int
    avg_pace_sec_per_km: float
    avg_heart_rate: float
    date: datetime.date
```

**`NextSessionSnapshot`**
```python
class NextSessionSnapshot(BaseModel):
    title: str
    date: datetime.date
```

**`DashboardSummary`**
```python
class DashboardSummary(BaseModel):
    whoop: WhoopSnapshot | None
    last_run: LastRunSnapshot | None
    next_session: NextSessionSnapshot | None
```

**`get_whoop_snapshot(conn)`**
```sql
SELECT recovery_score, sleep_performance_pct, daily_strain, date
FROM whoop_recovery_daily
ORDER BY date DESC
LIMIT 1
```

**`get_last_run_snapshot(conn)`**
```sql
SELECT distance_meters, duration_seconds, avg_pace_sec_per_km, avg_heart_rate, date
FROM activities
ORDER BY date DESC
LIMIT 1
```

**`get_next_session_snapshot(conn)`**
```sql
SELECT title, date
FROM google_calendar_runna_sessions
WHERE date >= CURRENT_DATE
ORDER BY date ASC
LIMIT 1
```

### `api/main.py`

New route: `GET /dashboard/summary`

```python
@app.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary() -> DashboardSummary:
    with get_connection() as conn:
        return DashboardSummary(
            whoop=get_whoop_snapshot(conn),
            last_run=get_last_run_snapshot(conn),
            next_session=get_next_session_snapshot(conn),
        )
```

### `ui/app.py`

On page load, calls `GET /dashboard/summary`. Replaces the `st.info("Charts will appear here")` placeholder with the three metric rows.

**Recovery score helper:**
```python
def _recovery_colour(score: float) -> str:
    if score >= 70:
        return "#4ade80"
    if score >= 40:
        return "#facc15"
    return "#f87171"
```

**Rendering:**
- Row 1: `st.columns(3)` — recovery (markdown + colour), sleep (`st.metric`), strain (`st.metric`)
- Row 2: `st.columns(4)` — distance, duration (formatted mm:ss), pace (formatted min:sec), bpm
- Row 3: title + date + days away inline

---

## Data Conversions (at read time in `dashboard.py`)

| Raw DB value | Displayed as |
|---|---|
| `distance_meters` | `distance_meters / 1000` → km (1 decimal) |
| `duration_seconds` | formatted as `mm:ss` |
| `avg_pace_sec_per_km` | formatted as `m:ss` |
| `date` (next session) | ISO date → "Wed 6 May" + days until |

---

## Error Handling

- `GET /dashboard/summary` returns HTTP 500 on DB error (standard FastAPI exception propagation).
- Streamlit wraps the fetch in a `try/except requests.RequestException` and shows `st.error()`.
- Each snapshot function returns `None` if its query returns no rows — the endpoint never raises for missing data.

---

## Testing

| Test | File | What it covers |
|---|---|---|
| Endpoint returns 200 with correct shape | `tests/test_dashboard_endpoint.py` | All three sections populated |
| Endpoint returns nulls when no data | `tests/test_dashboard_endpoint.py` | Empty DB → `whoop/last_run/next_session` all `null` |
| Recovery colour helper | `tests/test_dashboard_endpoint.py` | ≥70 → green, 40–69 → yellow, <40 → red |

All tests use `unittest.mock.patch` — no real DB calls.

---

## Files Changed

| File | Change |
|---|---|
| `api/dashboard.py` | **Create** — query functions + response models |
| `api/main.py` | **Modify** — add `GET /dashboard/summary` route |
| `ui/app.py` | **Modify** — replace dashboard placeholder with metric rows |
| `tests/test_dashboard_endpoint.py` | **Create** — endpoint + colour helper tests |

---

## Out of Scope

- Historical charts or trend lines
- Pace zone breakdowns
- Linking last run to its planned session
- Auto-refresh / polling
