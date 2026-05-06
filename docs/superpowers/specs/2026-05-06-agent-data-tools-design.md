# Agent Data Query Tools — Design Spec

**Date:** 2026-05-06
**Status:** Approved

## Goal

Give the LangGraph agent two data query tools so it can answer questions about recent
training and recovery, and about upcoming planned sessions. Currently the agent has no
way to read data from the database — it can only refresh ingestion and write memory.

## Architecture

Query functions live in a new `agent/queries.py` module. Each function accepts a
SQLAlchemy `Connection` and returns a formatted plain-text string that the LLM reads
directly as tool output. Tool wrappers in `agent/tools.py` open a DB connection and
call the query functions — same pattern as `api/dashboard.py`.

## File Map

| Action | Path | Change |
|--------|------|--------|
| Create | `agent/queries.py` | `get_training_and_recovery()` and `get_upcoming_sessions()` functions |
| Modify | `agent/tools.py` | Two new `@tool` wrappers, update `get_tools()` |
| Modify | `agent/prompts.py` | Add data query tool guidance and time-window rules |
| Create | `tests/test_agent_queries.py` | 6 unit tests with mock connections |

## Tool 1 — `get_training_and_recovery(lookback_days=7)`

### Purpose

Returns recent training and Whoop recovery data. The tool covers every question that
touches either runs or recovery — the agent should reach for it even when the question
is only about runs or only about recovery.

### SQL

`whoop_recovery_daily` drives the query so rest days (no run) still appear. Strava
activities are LEFT JOINed on date. On days with multiple runs the longest by distance
is kept.

```sql
SELECT
    w.date,
    w.recovery_score,
    w.hrv_rmssd_ms,
    w.resting_heart_rate,
    w.sleep_performance_pct,
    w.sleep_duration_ms,
    w.daily_strain,
    s.name          AS run_name,
    s.distance_meters,
    s.duration_seconds,
    s.avg_pace_sec_per_km,
    s.avg_heart_rate,
    s.efficiency_factor
FROM whoop_recovery_daily w
LEFT JOIN (
    SELECT DISTINCT ON (date)
        date, name, distance_meters, duration_seconds,
        avg_pace_sec_per_km, avg_heart_rate, efficiency_factor
    FROM strava_activities
    WHERE date >= CURRENT_DATE - :lookback_days * INTERVAL '1 day'
    ORDER BY date, distance_meters DESC NULLS LAST
) s ON s.date = w.date
WHERE w.date >= CURRENT_DATE - :lookback_days * INTERVAL '1 day'
ORDER BY w.date DESC
```

### Output format

One block per day, date as header, most recent first:

```
--- 2026-05-05 (Mon) ---
Recovery: 78% | HRV: 62ms | Resting HR: 48bpm | Sleep: 85% (6h 45m) | Strain: 12.3
Run: "Morning Run" · 10.2km in 58:30 | Pace: 5:44/km | Avg HR: 152bpm | EF: 1.42

--- 2026-05-04 (Sun) ---
Recovery: 65% | HRV: 55ms | Resting HR: 51bpm | Sleep: 72% (5h 50m) | Strain: 8.1
No run recorded.
```

Null Whoop fields render as `N/A`. If no data at all: `"No training or recovery data found for the last {lookback_days} days."`

### Guardrails

The guard runs **before** the DB call — the function returns the error string immediately
without opening a connection.

- `lookback_days > 90` → return `"Error: maximum lookback is 90 days (3 months). Ask the user to confirm a shorter window."` (no exception raised — the LLM reads it and self-corrects).

### Tool docstring (agent routing)

> Use for ANY question about recent training or recovery — including runs (distance,
> pace, heart rate, efficiency factor), Whoop recovery scores, HRV, resting heart rate,
> sleep performance or duration, daily strain, or the relationship between any of these.
> Use it even when the question is only about runs or only about recovery.

---

## Tool 2 — `get_upcoming_sessions(days_ahead=7)`

### Purpose

Returns planned training sessions from Google Calendar for a forward-looking window.
Covers all planning questions: next session, weekly overview, what's on a specific date.

### SQL

```sql
SELECT date, title, description
FROM google_calendar_runna_sessions
WHERE date >= CURRENT_DATE
  AND date <= CURRENT_DATE + :days_ahead * INTERVAL '1 day'
ORDER BY date ASC
```

### Output format

One block per session, date as header, soonest first:

```
--- 2026-05-07 (Wed) ---
Easy Run
45min easy effort, stay in zone 2, HR cap 145bpm

--- 2026-05-09 (Fri) ---
Tempo Intervals
5x1km at threshold pace with 90s recovery
```

If no sessions: `"No upcoming sessions in the next {days_ahead} days."`

### Guardrails

The guard runs **before** the DB call.

- `days_ahead > 90` → return `"Error: maximum window is 90 days (3 months). Ask the user to confirm a shorter window."`

### Tool docstring (agent routing)

> Use for ANY question about upcoming training sessions — next session, weekly training
> overview, what is planned on a specific date, or how many sessions are coming up.
> Default window is 7 days; increase days_ahead for a longer planning horizon (max 90 days).

---

## Time-Window Rules (system prompt)

Both tools share the same three-tier policy enforced via the system prompt:

| Window | Agent behaviour |
|--------|----------------|
| ≤ 30 days | Call the tool directly |
| 31–90 days | Ask the user to confirm before calling |
| > 90 days | Decline; explain the 3-month limit |

Default for both tools is **7 days** unless the user specifies otherwise.

---

## Testing

Six unit tests in `tests/test_agent_queries.py` using the `_mock_row` helper pattern
from `tests/test_dashboard_endpoint.py`:

| Test | What it checks |
|------|---------------|
| `test_get_training_and_recovery_with_run` | 2 rows (one with run, one rest day) → correct date headers and field values |
| `test_get_training_and_recovery_no_data` | Empty result set → no-data message |
| `test_get_training_and_recovery_rejects_over_90_days` | `lookback_days=91` → error string, DB never called |
| `test_get_upcoming_sessions_returns_sessions` | 2 sessions → correct date headers and titles |
| `test_get_upcoming_sessions_no_sessions` | Empty result set → no-sessions message |
| `test_get_upcoming_sessions_rejects_over_90_days` | `days_ahead=91` → error string, DB never called |

---

## Design notes (for capstone write-up)

**Why `agent/queries.py`?** Separating SQL from LangChain wiring follows the same
pattern as `api/dashboard.py` — query logic is independently testable with a mock
connection, and the tool wrapper stays a thin decorator. This keeps each module focused:
`queries.py` owns data retrieval, `tools.py` owns LangChain registration.

**Why one broad tool instead of split tools?** LLM tool selection is driven by the
docstring. Two separate tools (`get_recent_runs` + `get_whoop_scores`) force the agent
to reason about which to call for every question — and risk the wrong choice for
correlation questions. A single tool with a broad docstring eliminates that ambiguity.
`whoop_recovery_daily` drives the join so rest days appear even when the question is
purely about recovery.

**Why hard-cap at 90 days?** The agent context window is finite. 90 days of daily
entries (Whoop + runs) is roughly 90 blocks of text — enough for any meaningful trend
analysis without risking context overflow or querying data that doesn't exist.

## Out of scope

- Weekly aggregation (already handled by `weekly_summary` table if needed later)
- Filtering by session type or run type
- Date-range queries (start date + end date) — lookback window is sufficient for V0
- Pagination of tool output
