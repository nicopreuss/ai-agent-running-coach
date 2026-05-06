# Weekly Efficiency Factor Chart — Design Spec

**Date:** 2026-05-06
**Status:** Approved

## Goal

Add a "Weekly EF" line chart to the dashboard showing the duration-weighted average
Efficiency Factor per ISO week over the last 13 weeks (≈3 months).

## Formula

```
weekly_ef = SUM(efficiency_factor_i * duration_seconds_i) / SUM(duration_seconds_i)
```

Each run already has `efficiency_factor` pre-computed. The aggregation is a
duration-weighted average so longer runs contribute more than short ones.
Weeks with no EF-eligible runs (all runs missing HR data) are excluded from the chart.

## Chart

- **Type:** Line chart with dots at each data point
- **X axis:** Week start date, formatted `%b %d` (e.g. "Feb 3")
- **Y axis:** Weekly EF, zero-suppressed (starts near the actual min value)
- **Colour:** `#4ade80` (matches existing green aesthetic)
- **Tooltip:** Week + EF to 2 decimal places on hover
- **Height:** 200 px, full container width
- **Library:** Altair via `st.altair_chart`

## SQL query

```sql
SELECT
    DATE_TRUNC('week', date)::DATE AS week_start,
    SUM(efficiency_factor * duration_seconds) / SUM(duration_seconds) AS weekly_ef
FROM strava_activities
WHERE date >= CURRENT_DATE - INTERVAL '13 weeks'
  AND efficiency_factor IS NOT NULL
  AND duration_seconds IS NOT NULL
  AND duration_seconds > 0
GROUP BY DATE_TRUNC('week', date)
ORDER BY week_start ASC
```

`DATE_TRUNC('week', ...)` returns ISO Monday. The `::DATE` cast strips the time component
so the Pydantic model receives a plain `date`.

## Files touched

| File | Change |
|------|--------|
| `api/dashboard.py` | Add `WeeklyEFPoint` model + `get_weekly_ef_trend()` function |
| `api/main.py` | Add `GET /dashboard/weekly-ef` route |
| `ui/app.py` | New WEEKLY EF section below Next Session, Altair chart |
| `tests/test_dashboard_endpoint.py` | 2 new tests for `get_weekly_ef_trend` |

## Component details

### api/dashboard.py — WeeklyEFPoint

```python
class WeeklyEFPoint(BaseModel):
    week_start: datetime.date
    weekly_ef: float
```

### api/dashboard.py — get_weekly_ef_trend()

```python
def get_weekly_ef_trend(conn: Connection) -> list[WeeklyEFPoint]:
    rows = (
        conn.execute(
            text(
                """
                SELECT
                    DATE_TRUNC('week', date)::DATE AS week_start,
                    SUM(efficiency_factor * duration_seconds) / SUM(duration_seconds) AS weekly_ef
                FROM strava_activities
                WHERE date >= CURRENT_DATE - INTERVAL '13 weeks'
                  AND efficiency_factor IS NOT NULL
                  AND duration_seconds IS NOT NULL
                  AND duration_seconds > 0
                GROUP BY DATE_TRUNC('week', date)
                ORDER BY week_start ASC
                """
            )
        )
        .mappings()
        .all()
    )
    return [WeeklyEFPoint(week_start=r["week_start"], weekly_ef=r["weekly_ef"]) for r in rows]
```

### api/main.py — route

```python
@app.get("/dashboard/weekly-ef")
def weekly_ef_endpoint():
    with get_connection() as conn:
        return get_weekly_ef_trend(conn)
```

### ui/app.py — WEEKLY EF section

Placed after the Next Session divider. Calls `GET /dashboard/weekly-ef`, converts
the response to a Pandas DataFrame, renders an Altair line chart.

```python
st.divider()
st.caption("WEEKLY EFFICIENCY FACTOR · LAST 3 MONTHS")
try:
    resp = requests.get(f"{_API_BASE_URL}/dashboard/weekly-ef", timeout=10)
    resp.raise_for_status()
    points = resp.json()
except requests.RequestException as exc:
    st.error(f"Could not load weekly EF: {exc}")
    points = []

if points:
    import altair as alt
    import pandas as pd

    df = pd.DataFrame(points)
    df["week_start"] = pd.to_datetime(df["week_start"])
    chart = (
        alt.Chart(df)
        .mark_line(color="#4ade80", point=alt.OverlayMarkDef(color="#4ade80", size=50))
        .encode(
            x=alt.X("week_start:T", title="Week", axis=alt.Axis(format="%b %d")),
            y=alt.Y("weekly_ef:Q", title="EF", scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("week_start:T", title="Week", format="%b %d"),
                alt.Tooltip("weekly_ef:Q", title="EF", format=".2f"),
            ],
        )
        .properties(height=200)
    )
    st.altair_chart(chart, use_container_width=True)
else:
    st.caption("No efficiency data yet.")
```

## Testing

Two unit tests added to `tests/test_dashboard_endpoint.py`:

1. `test_get_weekly_ef_trend_returns_data` — mock `conn.execute` returning two rows;
   assert the result is a list of two `WeeklyEFPoint` with correct `week_start` and
   `weekly_ef` values.

2. `test_get_weekly_ef_trend_returns_empty_when_no_data` — mock returning no rows;
   assert result is `[]`.

## Out of scope

- Overlaying a trend/regression line
- Showing individual run dots on the same chart
- Filtering by run type (easy vs tempo vs long)
- Exporting the data
