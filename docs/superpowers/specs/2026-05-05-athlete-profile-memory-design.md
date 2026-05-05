# Athlete Profile & Memory System — Design Spec

**Date:** 2026-05-05  
**Branch:** feat/langgraph-migration  
**Status:** Approved

---

## Problem

The agent currently knows nothing about the athlete. Every conversation starts from zero —
no goals, no history, no preferences. There is no mechanism for the agent to build up
knowledge about the user over time.

---

## Goal

Give the agent a two-tier memory system inspired by OpenClaw:

- **Tier 1 (always loaded):** a curated athlete profile injected into every system prompt
- **Tier 2 (recent context):** daily session notes (today + yesterday) auto-loaded for temporal awareness

On first use, the agent onboards the athlete with structured questions and saves the answers
immediately. Over time, the profile grows through user-triggered updates and agent-initiated
daily observations.

---

## Design

### Two-tier memory model

| Tier | Content | Written by | Loaded |
|---|---|---|---|
| Tier 1 — `athlete_profile` | Permanent facts: goals, history, preferences, anything the athlete commits to long-term memory | User-triggered (`update_athlete_profile` tool) | Always — every conversation |
| Tier 2 — `session_notes` | Timestamped observations from the current session: feelings, incidental goals, noteworthy mentions | Agent-initiated (`add_session_note` tool) | Today + yesterday only |

The profile has no fixed schema — it is free-form Markdown text. The athlete can store
whatever they consider relevant.

---

### Database schema

Two new tables added to Supabase.

#### `athlete_profile`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | TEXT | `"default"` for single user; becomes auth ID in multi-user |
| content | TEXT | Free-form Markdown, appended on each update |
| updated_at | TIMESTAMPTZ | |
| UNIQUE(user_id) | | One profile per user |

#### `session_notes`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | TEXT | `"default"` for single user |
| date | DATE | |
| content | TEXT | Append-only observations for that day |
| updated_at | TIMESTAMPTZ | |
| UNIQUE(user_id, date) | | One note per user per day |

---

### Context injection

`load_athlete_context()` is called inside `build_agent()` before the system prompt is
assembled. It reads from Supabase and returns a formatted string:

```
## Athlete Profile
<content from athlete_profile where user_id = "default">

## Recent Session Notes
<content from session_notes where date = today>
<content from session_notes where date = yesterday>
```

This block is prepended to `SYSTEM_PROMPT` at agent build time (server startup / first request).
Profile updates made during a session are reflected on the next session. This is acceptable
because the onboarding flow progresses correctly within a single conversation via MemorySaver
message history — the agent sees its prior questions and answers and does not repeat them.

**First-run detection:** if the profile row is missing or its content is empty,
`load_athlete_context()` returns the onboarding instruction block instead (see below).

---

### Onboarding flow (first run)

When no profile exists, the system prompt includes:

```
## First-Run Onboarding
The athlete profile is empty. Before anything else, introduce yourself briefly and ask
the following questions one at a time. Save each answer to the athlete profile immediately
using the update_athlete_profile tool before asking the next question.

1. How long have you been running, and how would you describe your current level?
2. What is your main running goal right now? (race, time target, general fitness, etc.)
3. Do you have any current or recurring injuries I should know about?
4. How many days per week are you currently training?
5. How would you like me to coach you — encouraging and supportive, or direct and data-driven?
6. What should I call you?
```

Each answer is saved immediately — partial onboarding is preserved if the user drops off.
Once the profile is non-empty, the onboarding block is never injected again.

---

### Tools

#### `update_athlete_profile(fact: str)`

- **Trigger:** user explicitly says "remember that…" or similar
- **Behaviour:** fetches current profile content, appends the fact with a UTC timestamp, upserts back to `athlete_profile`
- **Example:** `"remember that my goal is to run the Paris Marathon in April 2027 under 4 hours"`

#### `add_session_note(note: str)`

- **Trigger:** agent observes something noteworthy during conversation (feeling, incidental goal hint, recovery mention, complaint about fatigue)
- **Behaviour:** fetches today's session note row (or creates it), appends the timestamped observation, upserts back to `session_notes`
- **Example:** agent notes `"athlete mentioned feeling tight in their left calf after yesterday's tempo run"`
- **System prompt instruction:** the agent is told to use this tool proactively whenever the athlete mentions something that would be useful context in a future conversation

---

### Module structure

New file: `agent/memory.py`

Responsibilities:
- `load_athlete_context(user_id: str = "default") -> str` — reads profile + daily notes from DB, returns formatted context block or onboarding block
- `update_athlete_profile(fact: str, user_id: str = "default") -> str` — append-and-upsert to `athlete_profile`
- `add_session_note(note: str, user_id: str = "default") -> str` — append-and-upsert to `session_notes`

`agent/agent.py` changes:
- Call `load_athlete_context()` and prepend result to `SYSTEM_PROMPT` at `build_agent()` time

`agent/tools.py` changes:
- Register `update_athlete_profile` and `add_session_note` as LangChain tools

`agent/prompts.py` changes:
- Add instructions telling the agent when to call each tool

`db/models.py` changes:
- Add SQLAlchemy models for `athlete_profile` and `session_notes`

`scripts/create_tables.py` changes:
- Create the two new tables

---

## Future work

### Short term
- **Agent-initiated profile updates (Tier 1):** allow the agent to proactively save permanent facts without explicit user instruction, using judgment from the system prompt. Currently deferred in favour of explicit user-triggered saves.
- **End-of-session summary:** a user command ("summarise today's session") that writes a structured recap to the daily note.

### Multi-user evolution
When extending to multiple users, the following changes are needed:

1. Add `user_id` column to all existing tables: `activities`, `whoop_recovery_daily`, `planned_sessions`, `weekly_summary`, `ingestion_log`
2. Replace `user_id = "default"` with an auth-derived user identifier throughout
3. Add authentication middleware to the FastAPI layer
4. Scope all agent tool queries by `user_id`

The `user_id` column in `athlete_profile` and `session_notes` is already in place — no migration needed for those tables when the time comes.

---

## Out of scope (this feature)

- Adding `user_id` to the existing 5 ingestion tables (separate migration, tracked as future work above)
- Tier 3 deep memory (knowledge graphs, embeddings, Cognee/Mem0 integration)
- Automatic promotion of daily notes to profile ("dreaming")
- Context compaction when profile grows large
