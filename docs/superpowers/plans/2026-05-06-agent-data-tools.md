# Agent Data Query Tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two data query tools (`get_training_and_recovery` and `get_upcoming_sessions`) to the LangGraph agent so it can answer questions about recent runs, Whoop recovery data, and upcoming planned sessions.

**Architecture:** SQL query functions in a new `agent/queries.py` module accept a SQLAlchemy `Connection` and return a formatted plain-text string. Thin `@tool` wrappers in `agent/tools.py` open a DB connection and call them. System prompt updated with routing instructions and time-window guardrails.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 (`text()`), LangChain `@tool`, `unittest.mock`, pytest.

---

## File Map

| Action | Path | Change |
|--------|------|--------|
| Create | `agent/queries.py` | `get_training_and_recovery()` + `get_upcoming_sessions()` + formatting helpers |
| Modify | `agent/tools.py` | Two new `@tool` wrappers, import `get_connection`, update `get_tools()` |
| Modify | `agent/prompts.py` | Add data query tool routing + time-window rules |
| Create | `tests/test_agent_queries.py` | 6 unit tests with mock connections |

---

## Task 1: `get_training_and_recovery` — tests + implementation

**Files:**
- Create: `tests/test_agent_queries.py`
- Create: `agent/queries.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent_queries.py`:

```python
"""Unit tests for agent.queries — mock DB connections, no real DB required."""

import datetime
from unittest.mock import MagicMock

from agent.queries import get_training_and_recovery, get_upcoming_sessions


def _mock_row(data: dict):
    row = MagicMock()
    row.__getitem__ = lambda self, k: data[k]
    return row


def test_get_training_and_recovery_with_run_and_rest_day():
    row_run = _mock_row({
        "date": datetime.date(2026, 5, 5),
        "recovery_score": 78.0,
        "hrv_rmssd_ms": 62.0,
        "resting_heart_rate": 48.0,
        "sleep_performance_pct": 85.0,
        "sleep_duration_ms": 24300000,
        "daily_strain": 12.3,
        "run_name": "Morning Run",
        "distance_meters": 10200.0,
        "duration_seconds": 3510,
        "avg_pace_sec_per_km": 344.0,
        "avg_heart_rate": 152.0,
        "efficiency_factor": 1.42,
    })
    row_rest = _mock_row({
        "date": datetime.date(2026, 5, 4),
        "recovery_score": 65.0,
        "hrv_rmssd_ms": 55.0,
        "resting_heart_rate": 51.0,
        "sleep_performance_pct": 72.0,
        "sleep_duration_ms": 21000000,
        "daily_strain": 8.1,
        "run_name": None,
        "distance_meters": None,
        "duration_seconds": None,
        "avg_pace_sec_per_km": None,
        "avg_heart_rate": None,
        "efficiency_factor": None,
    })
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = [row_run, row_rest]

    result = get_training_and_recovery(conn, lookback_days=7)

    assert "2026-05-05 (Mon)" in result
    assert "2026-05-04 (Sun)" in result
    assert "Recovery: 78%" in result
    assert "Morning Run" in result
    assert "10.2km" in result
    assert "No run recorded." in result


def test_get_training_and_recovery_no_data():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = []

    result = get_training_and_recovery(conn, lookback_days=7)

    assert "No training or recovery data" in result


def test_get_training_and_recovery_rejects_over_90_days():
    conn = MagicMock()

    result = get_training_and_recovery(conn, lookback_days=91)

    assert "Error" in result
    assert "90 days" in result
    conn.execute.assert_not_called()


def test_get_upcoming_sessions_returns_sessions():
    row1 = _mock_row({
        "date": datetime.date(2026, 5, 7),
        "title": "Easy Run",
        "description": "45min easy effort, HR cap 145bpm",
    })
    row2 = _mock_row({
        "date": datetime.date(2026, 5, 9),
        "title": "Tempo Intervals",
        "description": None,
    })
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = [row1, row2]

    result = get_upcoming_sessions(conn, days_ahead=7)

    assert "2026-05-07 (Wed)" in result
    assert "Easy Run" in result
    assert "45min easy effort" in result
    assert "2026-05-09 (Fri)" in result
    assert "Tempo Intervals" in result


def test_get_upcoming_sessions_no_sessions():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = []

    result = get_upcoming_sessions(conn, days_ahead=7)

    assert "No upcoming sessions" in result


def test_get_upcoming_sessions_rejects_over_90_days():
    conn = MagicMock()

    result = get_upcoming_sessions(conn, days_ahead=91)

    assert "Error" in result
    assert "90 days" in result
    conn.execute.assert_not_called()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_agent_queries.py::test_get_training_and_recovery_with_run_and_rest_day tests/test_agent_queries.py::test_get_training_and_recovery_no_data tests/test_agent_queries.py::test_get_training_and_recovery_rejects_over_90_days -v
```

Expected: 3 FAIL — `ImportError: cannot import name 'get_training_and_recovery'`.

- [ ] **Step 3: Create `agent/queries.py` with `get_training_and_recovery` and its helpers**

Create `agent/queries.py`:

```python
"""SQL query functions for the agent's data tools.

Each function accepts a SQLAlchemy Connection and returns a formatted plain-text string
that the LLM reads directly as tool output.
"""

import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection


def get_training_and_recovery(conn: Connection, lookback_days: int = 7) -> str:
    """Return formatted training and recovery data for the last *lookback_days* days."""
    if lookback_days > 90:
        return (
            "Error: maximum lookback is 90 days (3 months). "
            "Ask the user to confirm a shorter window."
        )

    rows = (
        conn.execute(
            text(
                """
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
                LEFT JOIN LATERAL (
                    SELECT name, distance_meters, duration_seconds,
                           avg_pace_sec_per_km, avg_heart_rate, efficiency_factor
                    FROM strava_activities
                    WHERE date = w.date
                    ORDER BY distance_meters DESC NULLS LAST
                    LIMIT 1
                ) s ON TRUE
                WHERE w.date >= CURRENT_DATE - (:lookback_days || ' days')::INTERVAL
                ORDER BY w.date DESC
                """
            ),
            {"lookback_days": lookback_days},
        )
        .mappings()
        .all()
    )

    if not rows:
        return f"No training or recovery data found for the last {lookback_days} days."

    return "\n\n".join(_fmt_day(row) for row in rows)


def get_upcoming_sessions(conn: Connection, days_ahead: int = 7) -> str:
    """Return formatted upcoming planned sessions for the next *days_ahead* days."""
    if days_ahead > 90:
        return (
            "Error: maximum window is 90 days (3 months). "
            "Ask the user to confirm a shorter window."
        )

    rows = (
        conn.execute(
            text(
                """
                SELECT date, title, description
                FROM google_calendar_runna_sessions
                WHERE date >= CURRENT_DATE
                  AND date <= CURRENT_DATE + (:days_ahead || ' days')::INTERVAL
                ORDER BY date ASC
                """
            ),
            {"days_ahead": days_ahead},
        )
        .mappings()
        .all()
    )

    if not rows:
        return f"No upcoming sessions in the next {days_ahead} days."

    return "\n\n".join(_fmt_session(row) for row in rows)


def _fmt_day(row) -> str:
    day_label = row["date"].strftime("%Y-%m-%d (%a)")
    recovery_line = _fmt_recovery(row)
    run_line = _fmt_run(row) if row["distance_meters"] is not None else "No run recorded."
    return f"--- {day_label} ---\n{recovery_line}\n{run_line}"


def _fmt_recovery(row) -> str:
    recovery = f"{row['recovery_score']:.0f}%" if row["recovery_score"] is not None else "N/A"
    hrv = f"{row['hrv_rmssd_ms']:.0f}ms" if row["hrv_rmssd_ms"] is not None else "N/A"
    rhr = f"{row['resting_heart_rate']:.0f}bpm" if row["resting_heart_rate"] is not None else "N/A"
    sleep = _fmt_sleep(row["sleep_performance_pct"], row["sleep_duration_ms"])
    strain = f"{row['daily_strain']:.1f}" if row["daily_strain"] is not None else "N/A"
    parts = [
        f"Recovery: {recovery}",
        f"HRV: {hrv}",
        f"Resting HR: {rhr}",
        f"Sleep: {sleep}",
        f"Strain: {strain}",
    ]
    return " | ".join(parts)


def _fmt_sleep(pct, ms) -> str:
    if pct is None:
        return "N/A"
    label = f"{pct:.0f}%"
    if ms is not None:
        total_min = ms // 60000
        h, m = divmod(total_min, 60)
        label += f" ({h}h {m:02d}m)"
    return label


def _fmt_run(row) -> str:
    km = row["distance_meters"] / 1000
    dur = _fmt_duration(row["duration_seconds"])
    pace = _fmt_pace(row["avg_pace_sec_per_km"])
    hr = f"{row['avg_heart_rate']:.0f}bpm" if row["avg_heart_rate"] is not None else "N/A"
    ef = f"{row['efficiency_factor']:.2f}" if row["efficiency_factor"] is not None else "N/A"
    name = row["run_name"] or "Run"
    return f'Run: "{name}" · {km:.1f}km in {dur} | Pace: {pace} | Avg HR: {hr} | EF: {ef}'


def _fmt_duration(seconds) -> str:
    if seconds is None:
        return "N/A"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_pace(sec_per_km) -> str:
    if sec_per_km is None:
        return "N/A"
    s = int(sec_per_km)
    return f"{s // 60}:{s % 60:02d}/km"


def _fmt_session(row) -> str:
    day_label = row["date"].strftime("%Y-%m-%d (%a)")
    title = row["title"] or "Untitled session"
    lines = [f"--- {day_label} ---", title]
    if row["description"]:
        lines.append(row["description"])
    return "\n".join(lines)
```

- [ ] **Step 4: Run the three tests to confirm they pass**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_agent_queries.py::test_get_training_and_recovery_with_run_and_rest_day tests/test_agent_queries.py::test_get_training_and_recovery_no_data tests/test_agent_queries.py::test_get_training_and_recovery_rejects_over_90_days -v
```

Expected: 3 PASS.

- [ ] **Step 5: Run the full test suite**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && git add agent/queries.py tests/test_agent_queries.py && git commit -m "feat: add get_training_and_recovery query function with tests"
```

---

## Task 2: `get_upcoming_sessions` — tests + implementation

**Files:**
- Modify: `tests/test_agent_queries.py` (tests already written in Task 1 Step 1)
- Modify: `agent/queries.py` (function already written in Task 1 Step 3)

Both functions and all 6 tests were written in Task 1. This task verifies the `get_upcoming_sessions` tests pass and commits.

- [ ] **Step 1: Run the three upcoming-sessions tests to confirm they pass**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_agent_queries.py::test_get_upcoming_sessions_returns_sessions tests/test_agent_queries.py::test_get_upcoming_sessions_no_sessions tests/test_agent_queries.py::test_get_upcoming_sessions_rejects_over_90_days -v
```

Expected: 3 PASS.

- [ ] **Step 2: Run the full test suite**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest --tb=short -q
```

Expected: all tests pass.

---

## Task 3: Wire tools + update prompt

**Files:**
- Modify: `agent/tools.py`
- Modify: `agent/prompts.py`

- [ ] **Step 1: Update `agent/tools.py`**

Replace the entire file with:

```python
"""Tool definitions for the LangChain agent."""

import os

import requests
from langchain_core.tools import tool

from agent.memory import add_session_note as _add_session_note
from agent.memory import update_athlete_profile as _update_athlete_profile
from agent.queries import get_training_and_recovery as _get_training_and_recovery
from agent.queries import get_upcoming_sessions as _get_upcoming_sessions
from db.client import get_connection

_API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

_SOURCE_LABELS = {
    "whoop": "Whoop",
    "strava": "Strava",
    "google_calendar": "Google Calendar",
}


@tool
def get_training_and_recovery(lookback_days: int = 7) -> str:
    """Use for ANY question about recent training or recovery — including runs (distance,
    pace, heart rate, efficiency factor), Whoop recovery scores, HRV, resting heart rate,
    sleep performance or duration, daily strain, or the relationship between any of these.
    Use it even when the question is only about runs or only about recovery.

    Args:
        lookback_days: How many days back to fetch. Default is 7. Increase for longer
            trend questions. Maximum is 90 days.

    Returns:
        Formatted text with one block per day showing recovery metrics and run details.
    """
    with get_connection() as conn:
        return _get_training_and_recovery(conn, lookback_days)


@tool
def get_upcoming_sessions(days_ahead: int = 7) -> str:
    """Use for ANY question about upcoming training sessions — next session, weekly
    training overview, what is planned on a specific date, or how many sessions are
    coming up. Default window is 7 days; increase days_ahead for a longer planning
    horizon (max 90 days).

    Args:
        days_ahead: How many days forward to look. Default is 7. Maximum is 90 days.

    Returns:
        Formatted text with one block per session showing date, title, and description.
    """
    with get_connection() as conn:
        return _get_upcoming_sessions(conn, days_ahead)


@tool
def refresh_data(source: str) -> str:
    """Fetch the latest data from Whoop, Strava, and/or Google Calendar and update the database.

    Use this tool when the user asks to refresh data, check if data is fresh,
    or explicitly requests pulling the latest recovery, activity, or training session records.

    Args:
        source: Which source to refresh — "whoop", "strava", "google_calendar", or "all".

    Returns:
        A plain-English summary of how many records were inserted.
    """
    sources = ["whoop", "strava", "google_calendar"] if source == "all" else [source]
    summaries = []

    for s in sources:
        response = requests.post(f"{_API_BASE_URL}/ingest/{s}", timeout=60)
        response.raise_for_status()
        data = response.json()
        n = data["records_inserted"]
        label = _SOURCE_LABELS.get(s, s.capitalize())
        if n == 0:
            summaries.append(f"{label}: already up to date.")
        elif n == 1:
            summaries.append(f"{label}: 1 new record inserted.")
        else:
            summaries.append(f"{label}: {n} new records inserted.")

    return " ".join(summaries)


@tool
def update_athlete_profile(fact: str) -> str:
    """Save a permanent fact to the athlete's profile.

    Call when the athlete explicitly says "remember that..." or asks you to save
    something to their profile. The fact is timestamped and appended.

    Args:
        fact: The fact or piece of information to save permanently.

    Returns:
        Confirmation that the fact was saved.
    """
    return _update_athlete_profile(fact)


@tool
def add_session_note(note: str) -> str:
    """Record a noteworthy observation from the current session.

    Call proactively when the athlete mentions something useful for future
    conversations: training feelings, fatigue, injuries, goal hints, or any
    relevant observation. The note is timestamped and appended to today's log.

    Args:
        note: The observation to record.

    Returns:
        Confirmation that the note was saved.
    """
    return _add_session_note(note)


def get_tools() -> list:
    """Return the list of tools registered with the agent."""
    return [
        get_training_and_recovery,
        get_upcoming_sessions,
        refresh_data,
        update_athlete_profile,
        add_session_note,
    ]
```

- [ ] **Step 2: Update `agent/prompts.py`**

Replace the entire file with:

```python
"""Prompt templates used by the agent."""

SYSTEM_PROMPT = """\
You are a personal AI running coach for a single athlete. \
You have access to the athlete's training data from Strava, recovery data from Whoop, \
and planned sessions from Google Calendar.

For questions about training history, performance, recovery, or upcoming sessions, \
always use your tools to retrieve real data before answering. Do not invent numbers.

For conversational questions (greetings, "who are you", general advice without \
specific data), answer directly without using a tool.

Keep answers concise and coach-like — actionable, data-grounded, and encouraging.

## Data query tools

Use get_training_and_recovery for ANY question that touches recent runs or Whoop data \
(recovery score, HRV, resting heart rate, sleep, strain). This includes questions about \
runs only, recovery only, or both together. Default lookback is 7 days.

Use get_upcoming_sessions for ANY question about planned training sessions — next \
session, weekly overview, or what is scheduled on a specific date. Default window is 7 days.

Time-window rules:
- Default to 7 days unless the user specifies otherwise.
- If the user asks for more than 30 days, confirm before calling the tool.
- If the user asks for more than 90 days, decline and explain the 3-month limit.

## Memory tools

Call update_athlete_profile when the athlete explicitly says "remember that..." or \
asks you to save something to their profile.

Call add_session_note proactively whenever the athlete mentions something worth \
remembering for future sessions: how they felt during training, fatigue, an injury \
hint, a new goal, or any context that would be useful in a future conversation.\
"""
```

- [ ] **Step 3: Run the full test suite**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && git add agent/tools.py agent/prompts.py && git commit -m "feat: wire get_training_and_recovery and get_upcoming_sessions tools into agent"
```

---

## Task 4: Push and raise PR

- [ ] **Step 1: Push the branch**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && git push -u origin feat/agent-data-tools
```

- [ ] **Step 2: Create the PR**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && gh pr create \
  --title "feat: add training/recovery and upcoming sessions query tools to agent" \
  --body "$(cat <<'EOF'
## Summary

- New `agent/queries.py` module with two query functions that accept a SQLAlchemy `Connection` and return formatted plain-text strings for the LLM
- `get_training_and_recovery(lookback_days=7)`: queries `whoop_recovery_daily` LEFT JOIN LATERAL `strava_activities`; Whoop-driven so rest days appear; one formatted block per day with recovery metrics + run details
- `get_upcoming_sessions(days_ahead=7)`: queries `google_calendar_runna_sessions` for upcoming sessions; one block per session with date, title, and description
- Both functions enforce a 90-day hard cap (return error string, DB never called)
- System prompt updated with explicit routing rules: use either tool for runs-only or recovery-only questions; confirm for >30 days, decline for >90 days
- `agent/tools.py` wired with two new `@tool` wrappers; `get_tools()` updated

## Test plan

- [ ] All tests pass (`poetry run pytest`)
- [ ] Start API and chat: ask "remind me my last run" — agent calls `get_training_and_recovery`
- [ ] Ask "how was my recovery this week?" — agent calls `get_training_and_recovery`
- [ ] Ask "what's my training plan this week?" — agent calls `get_upcoming_sessions`
- [ ] Ask "show me the last 6 months" — agent asks for confirmation
- [ ] Ask "show me the last 2 years" — agent declines and explains the 3-month limit

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
