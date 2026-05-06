# Weekly EF Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `GET /dashboard/weekly-ef` endpoint and an Altair line chart to the Streamlit dashboard showing the duration-weighted average Efficiency Factor per ISO week for the last 13 weeks.

**Architecture:** Three layers in dependency order — API model + query function first (with tests), then the FastAPI route, then the UI chart. No new DB columns; queries the existing `strava_activities` table.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 (`text()`), FastAPI/Pydantic, Streamlit + Altair 6.1.0, `unittest.mock`, pytest.

---

## File Map

| Action | Path | Change |
|--------|------|--------|
| Modify | `api/dashboard.py` | Add `WeeklyEFPoint` model + `get_weekly_ef_trend()` function |
| Modify | `tests/test_dashboard_endpoint.py` | Add 2 new tests for `get_weekly_ef_trend` |
| Modify | `api/main.py` | Add `GET /dashboard/weekly-ef` route |
| Modify | `ui/app.py` | New WEEKLY EF section below Next Session |

---

## Task 1: API — WeeklyEFPoint model + get_weekly_ef_trend()

**Files:**
- Modify: `api/dashboard.py` (add after `DashboardSummary` class, before `get_whoop_snapshot`)
- Modify: `tests/test_dashboard_endpoint.py` (append 2 new tests at the bottom)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_endpoint.py`:

```python
def test_get_weekly_ef_trend_returns_data():
    from api.dashboard import WeeklyEFPoint, get_weekly_ef_trend

    row1 = _mock_row({"week_start": datetime.date(2026, 2, 3), "weekly_ef": 1.42})
    row2 = _mock_row({"week_start": datetime.date(2026, 2, 10), "weekly_ef": 1.45})
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = [row1, row2]

    result = get_weekly_ef_trend(conn)

    assert len(result) == 2
    assert isinstance(result[0], WeeklyEFPoint)
    assert result[0].week_start == datetime.date(2026, 2, 3)
    assert result[0].weekly_ef == 1.42
    assert result[1].week_start == datetime.date(2026, 2, 10)
    assert result[1].weekly_ef == 1.45


def test_get_weekly_ef_trend_returns_empty_when_no_data():
    from api.dashboard import get_weekly_ef_trend

    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = []

    result = get_weekly_ef_trend(conn)

    assert result == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_dashboard_endpoint.py::test_get_weekly_ef_trend_returns_data tests/test_dashboard_endpoint.py::test_get_weekly_ef_trend_returns_empty_when_no_data -v
```

Expected: 2 FAIL — `ImportError: cannot import name 'WeeklyEFPoint'`.

- [ ] **Step 3: Add WeeklyEFPoint model and get_weekly_ef_trend() to api/dashboard.py**

In `api/dashboard.py`, add the new model and function after the `DashboardSummary` class (after line 38) and before `get_whoop_snapshot`. The new block to insert:

```python
class WeeklyEFPoint(BaseModel):
    week_start: datetime.date
    weekly_ef: float


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

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_dashboard_endpoint.py::test_get_weekly_ef_trend_returns_data tests/test_dashboard_endpoint.py::test_get_weekly_ef_trend_returns_empty_when_no_data -v
```

Expected: 2 PASS.

- [ ] **Step 5: Run the full test suite**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && git add api/dashboard.py tests/test_dashboard_endpoint.py && git commit -m "feat: add WeeklyEFPoint model and get_weekly_ef_trend() to dashboard API"
```

---

## Task 2: API — GET /dashboard/weekly-ef route

**Files:**
- Modify: `api/main.py` (add route + import after existing dashboard imports)

- [ ] **Step 1: Update the import in api/main.py**

In `api/main.py`, replace line 11:

```python
from api.dashboard import DashboardSummary, get_dashboard_summary
```

with:

```python
from api.dashboard import DashboardSummary, WeeklyEFPoint, get_dashboard_summary, get_weekly_ef_trend
from db.client import get_connection
```

- [ ] **Step 2: Add the route to api/main.py**

Append after the last route in `api/main.py` (after the `dashboard_summary` function):

```python
@app.get("/dashboard/weekly-ef", response_model=list[WeeklyEFPoint])
def weekly_ef_endpoint() -> list[WeeklyEFPoint]:
    """Return duration-weighted weekly EF for the last 13 weeks."""
    try:
        with get_connection() as conn:
            return get_weekly_ef_trend(conn)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
```

- [ ] **Step 3: Run the full test suite**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && git add api/main.py && git commit -m "feat: add GET /dashboard/weekly-ef route"
```

---

## Task 3: UI — Weekly EF Altair chart

**Files:**
- Modify: `ui/app.py` (add WEEKLY EF section inside `_render_dashboard()`, after the Next Session block)

- [ ] **Step 1: Add the Weekly EF section to _render_dashboard() in ui/app.py**

In `ui/app.py`, replace the closing of `_render_dashboard()` — the `else: st.caption("No upcoming sessions.")` block ends at line 106. The current end of the function is:

```python
    else:
        st.caption("No upcoming sessions.")
```

Replace with:

```python
    else:
        st.caption("No upcoming sessions.")

    st.divider()

    # ── Row 4: Weekly EF ──────────────────────────────────────────────────────
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

- [ ] **Step 2: Run the full test suite**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && git add ui/app.py && git commit -m "feat: add weekly EF Altair chart to dashboard"
```

---

## Task 4: Push and raise PR

- [ ] **Step 1: Push the branch**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && git push -u origin feat/weekly-ef-chart
```

- [ ] **Step 2: Create the PR**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && gh pr create \
  --title "feat: add weekly efficiency factor chart to dashboard" \
  --body "$(cat <<'EOF'
## Summary

- Adds `WeeklyEFPoint` Pydantic model and `get_weekly_ef_trend()` function to `api/dashboard.py`
- Duration-weighted weekly EF aggregation via `SUM(EF * duration) / SUM(duration)` over the last 13 weeks; weeks with no HR data are excluded
- New `GET /dashboard/weekly-ef` route in `api/main.py`
- Altair line chart (green `#4ade80`, zero-suppressed y-axis, `%b %d` x-axis, hover tooltip) rendered in the Streamlit dashboard below the Next Session section

## Test plan

- [ ] All tests pass (`poetry run pytest`)
- [ ] Start API + UI and confirm the chart appears in the dashboard
- [ ] Hover over data points to verify tooltip shows week and EF to 2 decimal places

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
