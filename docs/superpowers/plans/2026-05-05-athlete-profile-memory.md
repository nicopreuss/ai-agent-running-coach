# Athlete Profile & Memory System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the running coach agent a two-tier memory system — a persistent athlete profile (Tier 1, always loaded) and daily session notes (Tier 2, today + yesterday) — stored in Supabase, with first-run onboarding and user/agent-triggered writes.

**Architecture:** Two new Supabase tables (`athlete_profile`, `session_notes`) hold free-form Markdown text. At agent startup, `load_athlete_context()` reads both tiers from the DB and prepends the result to the system prompt. Two LangChain tools (`update_athlete_profile`, `add_session_note`) handle writes. If the profile is empty, the onboarding instruction block is injected instead.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0, psycopg2-binary, LangChain `@tool`, LangGraph `create_react_agent`, Supabase (Postgres).

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `db/models.py` | Add `AthleteProfile` and `SessionNote` ORM models |
| Create | `agent/memory.py` | `load_athlete_context`, `update_athlete_profile`, `add_session_note`, `_ONBOARDING_BLOCK` |
| Modify | `agent/prompts.py` | Add memory tool instructions to `SYSTEM_PROMPT` |
| Modify | `agent/tools.py` | Wrap memory functions as `@tool`, add to `get_tools()` |
| Modify | `agent/agent.py` | Call `load_athlete_context()` in `build_agent()` |
| Create | `tests/test_memory.py` | Unit tests for all memory functions (DB mocked) |
| Modify | `tests/test_tools.py` | Add tests for new memory tools in `get_tools()` |
| Modify | `tests/test_agent.py` | Add test that `build_agent()` injects athlete context |
| Create | `scripts/smoke_test_athlete_memory.py` | Manual end-to-end verification against real Supabase |

---

## Task 1: DB models for `athlete_profile` and `session_notes`

**Files:**
- Modify: `db/models.py`
- Test: `tests/test_memory.py` (model structure assertions — no DB required)

- [ ] **Step 1: Write the failing test**

Create `tests/test_memory.py` with:

```python
"""Tests for agent/memory.py."""

from db.models import AthleteProfile, SessionNote


def test_athlete_profile_table_name() -> None:
    assert AthleteProfile.__tablename__ == "athlete_profile"


def test_athlete_profile_columns() -> None:
    cols = {c.name for c in AthleteProfile.__table__.columns}
    assert cols == {"id", "user_id", "content", "updated_at"}


def test_athlete_profile_user_id_is_unique() -> None:
    unique_cols = {
        col
        for constraint in AthleteProfile.__table__.constraints
        if hasattr(constraint, "columns")
        for col in constraint.columns.keys()
    }
    assert "user_id" in unique_cols


def test_session_note_table_name() -> None:
    assert SessionNote.__tablename__ == "session_notes"


def test_session_note_columns() -> None:
    cols = {c.name for c in SessionNote.__table__.columns}
    assert cols == {"id", "user_id", "date", "content", "updated_at"}


def test_session_note_has_user_id_date_unique_constraint() -> None:
    from sqlalchemy import UniqueConstraint
    constraints = [
        c for c in SessionNote.__table__.constraints
        if isinstance(c, UniqueConstraint)
    ]
    unique_col_sets = [
        frozenset(c.columns.keys()) for c in constraints
    ]
    assert frozenset({"user_id", "date"}) in unique_col_sets
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_memory.py -v
```

Expected: `ImportError: cannot import name 'AthleteProfile' from 'db.models'`

- [ ] **Step 3: Add models to `db/models.py`**

Add this import at the top of the existing imports block:

```python
from sqlalchemy import UniqueConstraint
```

Then append these two classes at the bottom of `db/models.py`:

```python
class AthleteProfile(Base):
    __tablename__ = "athlete_profile"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SessionNote(Base):
    __tablename__ = "session_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (UniqueConstraint("user_id", "date"),)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_memory.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 5: Create the new tables in Supabase**

```bash
poetry run python -m scripts.create_tables
```

Expected output includes `athlete_profile` and `session_notes` in the tables list.

- [ ] **Step 6: Commit**

```bash
git add db/models.py tests/test_memory.py
git commit -m "feat: add AthleteProfile and SessionNote DB models"
```

---

## Task 2: `agent/memory.py` — core read/write functions

**Files:**
- Create: `agent/memory.py`
- Modify: `tests/test_memory.py` (append new tests)

- [ ] **Step 1: Write the failing tests**

First, add this import at the top of `tests/test_memory.py` (after the existing `from db.models` import):

```python
from unittest.mock import MagicMock, patch
```

Then append the following to the bottom of `tests/test_memory.py`:

```python
def _make_conn_mock(execute_side_effects: list) -> MagicMock:
    """Return a mock connection whose execute() calls return successive values."""
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = execute_side_effects
    return mock_conn


def _patch_conn(mock_conn: MagicMock):
    """Patch get_connection() to return mock_conn as a context manager."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=mock_conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return patch("agent.memory.get_connection", return_value=ctx)


# --- load_athlete_context ---

def test_load_athlete_context_returns_onboarding_when_no_profile() -> None:
    mock_conn = _make_conn_mock([
        MagicMock(**{"fetchone.return_value": None}),   # profile query
        MagicMock(**{"fetchall.return_value": []}),     # notes query (never reached)
    ])

    with _patch_conn(mock_conn):
        from agent.memory import load_athlete_context
        result = load_athlete_context()

    assert "First-Run Onboarding" in result
    assert "How long have you been running" in result


def test_load_athlete_context_returns_onboarding_when_content_empty() -> None:
    profile_row = MagicMock()
    profile_row.content = ""

    mock_conn = _make_conn_mock([
        MagicMock(**{"fetchone.return_value": profile_row}),
        MagicMock(**{"fetchall.return_value": []}),
    ])

    with _patch_conn(mock_conn):
        from agent.memory import load_athlete_context
        result = load_athlete_context()

    assert "First-Run Onboarding" in result


def test_load_athlete_context_returns_profile_and_notes() -> None:
    profile_row = MagicMock()
    profile_row.content = "Goal: Paris Marathon sub-4h"

    note_row = MagicMock()
    note_row.content = "- [10:00 UTC] felt fatigued after long run"

    mock_conn = _make_conn_mock([
        MagicMock(**{"fetchone.return_value": profile_row}),
        MagicMock(**{"fetchall.return_value": [note_row]}),
    ])

    with _patch_conn(mock_conn):
        from agent.memory import load_athlete_context
        result = load_athlete_context()

    assert "## Athlete Profile" in result
    assert "Paris Marathon" in result
    assert "## Recent Session Notes" in result
    assert "felt fatigued" in result


def test_load_athlete_context_omits_notes_section_when_no_notes() -> None:
    profile_row = MagicMock()
    profile_row.content = "Goal: Paris Marathon sub-4h"

    mock_conn = _make_conn_mock([
        MagicMock(**{"fetchone.return_value": profile_row}),
        MagicMock(**{"fetchall.return_value": []}),
    ])

    with _patch_conn(mock_conn):
        from agent.memory import load_athlete_context
        result = load_athlete_context()

    assert "## Athlete Profile" in result
    assert "## Recent Session Notes" not in result


# --- update_athlete_profile ---

def test_update_athlete_profile_returns_confirmation() -> None:
    mock_conn = _make_conn_mock([
        MagicMock(**{"fetchone.return_value": None}),  # read: no existing profile
        MagicMock(),                                   # write: upsert
    ])

    with _patch_conn(mock_conn):
        from agent.memory import update_athlete_profile
        result = update_athlete_profile("Goal: sub-4h marathon")

    assert "Saved to your profile" in result
    mock_conn.commit.assert_called_once()


def test_update_athlete_profile_commits_on_existing_profile() -> None:
    existing = MagicMock()
    existing.content = "- [2026-01-01 09:00 UTC] Goal: sub-4h marathon"

    mock_conn = _make_conn_mock([
        MagicMock(**{"fetchone.return_value": existing}),
        MagicMock(),
    ])

    with _patch_conn(mock_conn):
        from agent.memory import update_athlete_profile
        result = update_athlete_profile("I prefer morning runs")

    assert "Saved to your profile" in result
    mock_conn.commit.assert_called_once()


# --- add_session_note ---

def test_add_session_note_returns_confirmation() -> None:
    mock_conn = _make_conn_mock([
        MagicMock(**{"fetchone.return_value": None}),  # read: no existing note today
        MagicMock(),                                   # write: upsert
    ])

    with _patch_conn(mock_conn):
        from agent.memory import add_session_note
        result = add_session_note("athlete mentioned left calf tightness")

    assert "Session note saved" in result
    mock_conn.commit.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_memory.py -v -k "load_athlete or update_athlete or add_session"
```

Expected: `ImportError: cannot import name 'load_athlete_context' from 'agent.memory'`

- [ ] **Step 3: Create `agent/memory.py`**

```python
"""Athlete profile and session notes memory system.

Tier 1 (athlete_profile): permanent facts, always injected into the system prompt.
Tier 2 (session_notes): daily observations, today + yesterday auto-loaded.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql import func

from db.client import get_connection
from db.models import AthleteProfile, SessionNote

_DEFAULT_USER = "default"

_ONBOARDING_BLOCK = """\
## First-Run Onboarding
The athlete profile is empty. Before anything else, introduce yourself briefly and ask \
the following questions one at a time. Save each answer to the athlete profile immediately \
using the update_athlete_profile tool before asking the next question.

1. How long have you been running, and how would you describe your current level?
2. What is your main running goal right now? (race, time target, general fitness, etc.)
3. Do you have any current or recurring injuries I should know about?
4. How many days per week are you currently training?
5. How would you like me to coach you — encouraging and supportive, or direct and data-driven?
6. What should I call you?\
"""


def load_athlete_context(user_id: str = _DEFAULT_USER) -> str:
    """Return the formatted context block to prepend to the system prompt.

    Returns the onboarding block if the profile is missing or empty.
    """
    with get_connection() as conn:
        profile_row = conn.execute(
            select(AthleteProfile.content).where(AthleteProfile.user_id == user_id)
        ).fetchone()
        profile_content = profile_row.content if profile_row else None

        if not profile_content:
            return _ONBOARDING_BLOCK

        today = date.today()
        yesterday = today - timedelta(days=1)
        note_rows = conn.execute(
            select(SessionNote.content)
            .where(SessionNote.user_id == user_id)
            .where(SessionNote.date.in_([today, yesterday]))
            .order_by(SessionNote.date.desc())
        ).fetchall()

    parts = [f"## Athlete Profile\n{profile_content}"]
    if note_rows:
        parts.append("## Recent Session Notes")
        for row in note_rows:
            if row.content:
                parts.append(row.content)

    return "\n\n".join(parts)


def update_athlete_profile(fact: str, user_id: str = _DEFAULT_USER) -> str:
    """Append *fact* to the athlete's persistent profile in the DB."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"\n- [{timestamp}] {fact}"

    with get_connection() as conn:
        row = conn.execute(
            select(AthleteProfile.content).where(AthleteProfile.user_id == user_id)
        ).fetchone()
        current = row.content if row and row.content else ""
        new_content = current + entry

        conn.execute(
            pg_insert(AthleteProfile)
            .values(user_id=user_id, content=new_content, updated_at=func.now())
            .on_conflict_do_update(
                index_elements=["user_id"],
                set_={"content": new_content, "updated_at": func.now()},
            )
        )
        conn.commit()

    return f"Saved to your profile: {fact}"


def add_session_note(note: str, user_id: str = _DEFAULT_USER) -> str:
    """Append *note* to today's session note row in the DB."""
    today = date.today()
    timestamp = datetime.now(timezone.utc).strftime("%H:%M UTC")
    entry = f"\n- [{timestamp}] {note}"

    with get_connection() as conn:
        row = conn.execute(
            select(SessionNote.content)
            .where(SessionNote.user_id == user_id)
            .where(SessionNote.date == today)
        ).fetchone()
        current = row.content if row and row.content else ""
        new_content = current + entry

        conn.execute(
            pg_insert(SessionNote)
            .values(user_id=user_id, date=today, content=new_content, updated_at=func.now())
            .on_conflict_do_update(
                index_elements=["user_id", "date"],
                set_={"content": new_content, "updated_at": func.now()},
            )
        )
        conn.commit()

    return "Session note saved."
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_memory.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add agent/memory.py tests/test_memory.py
git commit -m "feat: add agent/memory.py with two-tier athlete profile system"
```

---

## Task 3: Update `agent/prompts.py` with memory tool instructions

**Files:**
- Modify: `agent/prompts.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_memory.py`:

```python
def test_system_prompt_includes_memory_tool_instructions() -> None:
    from agent.prompts import SYSTEM_PROMPT
    assert "update_athlete_profile" in SYSTEM_PROMPT
    assert "add_session_note" in SYSTEM_PROMPT
    assert "remember that" in SYSTEM_PROMPT.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_memory.py::test_system_prompt_includes_memory_tool_instructions -v
```

Expected: FAIL — `AssertionError`

- [ ] **Step 3: Update `agent/prompts.py`**

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

## Memory tools

Call update_athlete_profile when the athlete explicitly says "remember that..." or \
asks you to save something to their profile.

Call add_session_note proactively whenever the athlete mentions something worth \
remembering for future sessions: how they felt during training, fatigue, an injury \
hint, a new goal, or any context that would be useful in a future conversation.\
"""
```

- [ ] **Step 4: Run test to verify it passes**

```bash
poetry run pytest tests/test_memory.py::test_system_prompt_includes_memory_tool_instructions -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/prompts.py tests/test_memory.py
git commit -m "feat: add memory tool instructions to system prompt"
```

---

## Task 4: Register memory tools in `agent/tools.py`

**Files:**
- Modify: `agent/tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tools.py`:

```python
def test_get_tools_contains_update_athlete_profile() -> None:
    tools = get_tools()
    tool_names = [t.name for t in tools]
    assert "update_athlete_profile" in tool_names


def test_get_tools_contains_add_session_note() -> None:
    tools = get_tools()
    tool_names = [t.name for t in tools]
    assert "add_session_note" in tool_names
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_tools.py -v
```

Expected: last two tests FAIL — `AssertionError`

- [ ] **Step 3: Update `agent/tools.py`**

Replace the entire file with:

```python
"""Tool definitions for the LangChain agent."""

import os

import requests
from langchain_core.tools import tool

from agent.memory import add_session_note as _add_session_note
from agent.memory import update_athlete_profile as _update_athlete_profile

_API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

_SOURCE_LABELS = {
    "whoop": "Whoop",
    "strava": "Strava",
    "google_calendar": "Google Calendar",
}


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
    """
    return _update_athlete_profile(fact)


@tool
def add_session_note(note: str) -> str:
    """Record a noteworthy observation from the current session.

    Call proactively when the athlete mentions something useful for future
    conversations: training feelings, fatigue, injuries, goal hints, or any
    relevant observation. Notes are timestamped and stored for today and yesterday.

    Args:
        note: The observation to record.
    """
    return _add_session_note(note)


def get_tools() -> list:
    """Return the list of tools registered with the agent."""
    return [refresh_data, update_athlete_profile, add_session_note]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_tools.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add agent/tools.py tests/test_tools.py
git commit -m "feat: register update_athlete_profile and add_session_note tools"
```

---

## Task 5: Wire context injection in `agent/agent.py`

**Files:**
- Modify: `agent/agent.py`
- Modify: `tests/test_agent.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_agent.py`, update the existing import line at the top from:

```python
from agent.agent import run
```

to:

```python
from agent.agent import build_agent, run
```

Then append this test to the bottom of `tests/test_agent.py`:

```python
def test_build_agent_injects_athlete_context() -> None:
    """build_agent() prepends athlete context to the system prompt."""
    mock_context = "## Athlete Profile\nGoal: Paris Marathon sub-4h"
    captured_prompts = []

    def capture_create(llm, **kwargs):
        captured_prompts.append(kwargs["prompt"])
        return MagicMock()

    with patch("agent.agent.load_athlete_context", return_value=mock_context):
        with patch("agent.agent.ChatOpenAI"):
            with patch("agent.agent.MemorySaver"):
                with patch("agent.agent.create_react_agent", side_effect=capture_create):
                    build_agent()

    assert len(captured_prompts) == 1
    assert "Athlete Profile" in captured_prompts[0].content
    assert "sub-4h" in captured_prompts[0].content
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_agent.py::test_build_agent_injects_athlete_context -v
```

Expected: FAIL — `ImportError` or `AssertionError` (load_athlete_context not imported yet)

- [ ] **Step 3: Update `agent/agent.py`**

Replace the entire file with:

```python
"""Core agent module: initializes the LangGraph ReAct agent and exposes a run() entrypoint."""

import logging
import os
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from agent.memory import load_athlete_context
from agent.prompts import SYSTEM_PROMPT
from agent.tools import get_tools

load_dotenv()

logger = logging.getLogger(__name__)

_SESSION_ID = str(uuid4())
_THREAD = {"configurable": {"thread_id": _SESSION_ID}}


def build_agent():
    """Instantiate and return the LangGraph ReAct agent with memory."""
    athlete_context = load_athlete_context()
    full_prompt = f"{athlete_context}\n\n---\n\n{SYSTEM_PROMPT}"

    llm = ChatOpenAI(
        model=os.environ["OPENAI_MODEL"],
        temperature=0,
        default_headers={"X-Session-ID": _SESSION_ID},
    )
    checkpointer = MemorySaver()
    return create_react_agent(
        llm,
        tools=get_tools(),
        prompt=SystemMessage(content=full_prompt),
        checkpointer=checkpointer,
    )


_agent = None


def run(query: str) -> dict[str, Any]:
    """Invoke the agent with *query* and return response text plus tool names used."""
    global _agent
    if _agent is None:
        _agent = build_agent()
    try:
        result = _agent.invoke(
            {"messages": [HumanMessage(content=query)]},
            config=_THREAD,
        )
        tools_used = [
            tc["name"]
            for msg in result["messages"]
            if msg.type == "ai"
            for tc in (msg.tool_calls or [])
        ]
        final = next(
            (
                msg.content
                for msg in reversed(result["messages"])
                if msg.type == "ai" and not msg.tool_calls
            ),
            "",
        )
        return {"response": final, "tools_used": tools_used}
    except Exception:
        logger.exception("Agent invocation failed for query: %s", query)
        raise
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
poetry run pytest tests/ -v
```

Expected: all tests PASS (the `test_build_agent_injects_athlete_context` new test now passes, all prior tests still pass)

- [ ] **Step 5: Commit**

```bash
git add agent/agent.py tests/test_agent.py
git commit -m "feat: inject athlete context into system prompt at agent build time"
```

---

## Task 6: Smoke test

**Files:**
- Create: `scripts/smoke_test_athlete_memory.py`

- [ ] **Step 1: Create the smoke test script**

```python
"""Smoke test for the athlete profile and session notes memory system.

Writes test entries to the real Supabase DB, reads them back, and prints a summary.
Run with: poetry run python -m scripts.smoke_test_athlete_memory
"""

from agent.memory import add_session_note, load_athlete_context, update_athlete_profile


def main() -> None:
    print("=== Athlete Memory Smoke Test ===\n")

    print("1. Loading current athlete context...")
    context = load_athlete_context()
    print(context[:600] if len(context) > 600 else context)
    print()

    print("2. Writing test fact to athlete profile...")
    result = update_athlete_profile("[SMOKE TEST] This entry verifies profile writes work")
    print(f"   {result}")
    print()

    print("3. Adding a session note for today...")
    result = add_session_note("[SMOKE TEST] Verifying session note writes work")
    print(f"   {result}")
    print()

    print("4. Reloading context to verify both writes are visible...")
    context = load_athlete_context()
    smoke_ok = "[SMOKE TEST]" in context
    print("   PASS — smoke test entries found in context." if smoke_ok else "   FAIL — smoke test entries NOT found in context.")
    print()
    print(context[:1200] if len(context) > 1200 else context)
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the smoke test against Supabase**

```bash
poetry run python -m scripts.smoke_test_athlete_memory
```

Expected output:
```
=== Athlete Memory Smoke Test ===

1. Loading current athlete context...
## First-Run Onboarding   ← (or existing profile if one exists)
...

2. Writing test fact to athlete profile...
   Saved to your profile: [SMOKE TEST] This entry verifies profile writes work

3. Adding a session note for today...
   Session note saved.

4. Reloading context to verify both writes are visible...
   PASS — smoke test entries found in context.
...
=== Done ===
```

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_test_athlete_memory.py
git commit -m "feat: add smoke test for athlete memory system"
```
