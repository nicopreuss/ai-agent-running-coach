# Running Coach AI — CLAUDE.md

## Project purpose

A personal running coach AI agent built for the DataExpert.io AI Engineer Bootcamp capstone.
It ingests training and physiological data from Strava, Whoop, and Google Calendar into a unified
Postgres schema, then exposes a LangChain agent that can answer analytical questions about
training, recovery, and upcoming sessions.

**This is a single-user personal project, not a multi-user product.** The user is the only athlete.
OAuth tokens live in environment variables. There is no auth layer, no per-user isolation, no
row-level security.

**Goal:** Showcase-quality code for a bootcamp presentation. High-quality, clean, and readable.
Not production-grade. Do not over-engineer. Prefer simple and explicit over clever and abstract.

---

## Design philosophy

- Keep code clean and readable — a reviewer seeing it for the first time should follow it easily
- Use real SWE patterns (ABC, typed functions, proper error handling, clear separation of concerns)
- Do not over-engineer — no premature abstractions, no unnecessary layers, no "just in case" code
- Single user means no multi-tenancy complexity anywhere
- When in doubt, choose the simpler approach

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Package manager | Poetry |
| Database | Postgres via Supabase (free tier) |
| ORM | SQLAlchemy 2.0 |
| Agent framework | LangChain (ReAct agent) |
| LLM | OpenAI GPT-4o |
| API backend | FastAPI |
| Frontend | Streamlit (fast MVP) |
| Scheduler | APScheduler (nightly batch at 06:00) |
| Tracing | LangSmith |
| Hosting | Render |

---

## Data sources

### Strava API v3
- Auth: OAuth 2.0, scope `activity:read`
- Pulls completed running activities (filter: `type = Run`)
- Rate limits: 100 req/15 min, 1,000 req/day — not a concern for single user
- Key fields: distance, moving_time, avg heart rate, cadence, elevation, suffer_score, start_date
- Pagination: `before`/`after` epoch timestamps

### Whoop API v2
- Auth: OAuth 2.0, 6 scopes
- Pulls: cycles, recovery, sleep, workouts
- Key fields: recovery_score, HRV RMSSD, resting HR, sleep stages, daily strain, SpO2
- Pagination: cursor-based `next_token`, max 25 records/page
- No webhooks — polling only

### Google Calendar (Runna sessions)
- Auth: OAuth 2.0, scope `calendar.readonly`
- Runna syncs planned training sessions to a dedicated Google Calendar
- Each event has session type and targets in the title/description
- At ingestion: one LLM call classifies session type → stored as enum, not re-parsed at query time
- Rolling window: 30 days future + 180 days lookback

---

## Database schema (5 tables)

### `recovery_daily`
One row per calendar date. Morning health snapshot from Whoop.
Primary join key to `activities` is `date`.

| Column | Type | Notes |
|---|---|---|
| date | DATE PK | Join key |
| whoop_cycle_id | BIGINT UNIQUE | Dedup key |
| recovery_score | FLOAT | 0–100% |
| hrv_rmssd_ms | FLOAT | |
| resting_heart_rate | FLOAT | bpm |
| sleep_performance_pct | FLOAT | |
| sleep_efficiency_pct | FLOAT | |
| sleep_duration_ms | BIGINT | convert to hours in app |
| swo_deep_sleep_ms | BIGINT | slow-wave / deep |
| rem_sleep_ms | BIGINT | |
| light_sleep_ms | BIGINT | |
| sleep_consistency_pct | FLOAT | |
| daily_strain | FLOAT | 0–21 |
| skin_temp_celsius | FLOAT | nullable, Whoop 4.0+ |
| spo2_percentage | FLOAT | nullable, Whoop 4.0+ |
| created_at | TIMESTAMPTZ | |

### `activities`
One row per completed Strava run.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| strava_activity_id | BIGINT UNIQUE | Dedup key |
| date | DATE | FK → recovery_daily.date |
| start_time | TIMESTAMPTZ | |
| name | TEXT | |
| distance_meters | FLOAT | |
| duration_seconds | INT | moving time |
| elapsed_time_seconds | INT | |
| avg_pace_sec_per_km | FLOAT | derived at ingestion |
| avg_heart_rate | FLOAT | bpm |
| max_heart_rate | INT | bpm |
| avg_cadence | FLOAT | steps/min |
| elevation_gain_meters | FLOAT | |
| suffer_score | INT | Strava training load proxy |
| pr_count | INT | |
| perceived_effort | INT | nullable, 1–10 |
| created_at | TIMESTAMPTZ | |

### `planned_sessions`
One row per Runna session from Google Calendar. `completed` flipped when matching Strava activity found.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| google_event_id | TEXT UNIQUE | Dedup key |
| scheduled_date | DATE | |
| scheduled_start_time | TIMESTAMPTZ | nullable |
| title | TEXT | raw event title |
| description | TEXT | raw event description |
| session_type | ENUM | easy/tempo/intervals/long_run/rest |
| target_duration_minutes | INT | nullable, parsed from description |
| target_distance_km | FLOAT | nullable, parsed from description |
| completed | BOOLEAN | |
| strava_activity_id | BIGINT | nullable, FK if completed |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### `weekly_summary`
One row per ISO week. Recomputed at ingestion time — never aggregated at query time by the agent.

| Column | Type | Notes |
|---|---|---|
| week_start_date | DATE PK | Monday of ISO week |
| total_runs | INT | |
| total_distance_km | FLOAT | |
| total_duration_minutes | FLOAT | |
| avg_recovery_score | FLOAT | |
| avg_hrv | FLOAT | |
| avg_pace_sec_per_km | FLOAT | |
| total_elevation_meters | FLOAT | |
| training_load | INT | sum of suffer_score |
| easy_runs | INT | |
| tempo_runs | INT | |
| long_runs | INT | |
| interval_runs | INT | |
| planned_sessions_count | INT | |
| completed_sessions_count | INT | |
| completion_rate_pct | FLOAT | |
| created_at | TIMESTAMPTZ | |

### `ingestion_log`
One row per pipeline run per source. Provides watermark for incremental fetches.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| source | ENUM | whoop/strava/google_calendar |
| status | ENUM | success/partial/failed |
| records_fetched | INT | |
| records_inserted | INT | |
| records_skipped | INT | deduped |
| last_fetched_at | TIMESTAMPTZ | watermark for next run |
| error_message | TEXT | nullable |
| created_at | TIMESTAMPTZ | |

---

## Ingestion pipeline

- Runs nightly at **06:00** via APScheduler (after Whoop recovery is computed)
- **Incremental by default** — reads `last_fetched_at` watermark from `ingestion_log` per source
- **Backfill** — one-time CLI command that sets watermark to `None` and pulls full history
- **Idempotent** — all inserts use `INSERT ... ON CONFLICT DO NOTHING`
- **Derived fields computed at ingestion:** `avg_pace_sec_per_km`, `session_type` (LLM call), `completed` flag on planned sessions, `weekly_summary` recomputation

### Ingestion order per run
1. Read `last_fetched_at` watermark per source from `ingestion_log`
2. Refresh OAuth tokens if expired
3. Fetch Whoop: cycles → recovery → sleep
4. Fetch Strava: runs since watermark
5. Fetch Google Calendar: Runna events (±30 day window)
6. Normalize + derive computed fields
7. Upsert all records
8. Recompute `weekly_summary` for affected weeks
9. Write success record to `ingestion_log` with updated watermark
10. On failure: write error to `ingestion_log`, log and continue

---

## Agent layer

LangChain ReAct agent backed by three tools. Each tool runs SQL against Postgres and returns
structured results the agent cites in its response.

### Tool 1 — `get_recent_stats`
Answers exploratory questions about recent performance. Accepts a lookback window in days.
Example: "Give me a summary of my last 2 weeks", "How many km did I run last month?"

### Tool 2 — `analyze_performance_vs_recovery`
Joins `activities` and `recovery_daily` on `date` to surface correlations.
Example: "When my recovery is above 70%, how much faster do I run?", "What's my HR like after poor sleep?"

### Tool 3 — `get_upcoming_sessions`
Reads `planned_sessions` for a date range. Enables forward-looking reasoning.
Example: "What does my training week look like?", "I have low recovery — what's my session tomorrow?"

---

## UI

Two-panel Streamlit app:
- **Chat panel** — conversational interface backed by the agent, retains session history
- **Metrics dashboard** — read-only charts: recovery trend (14d), HRV trend, weekly training load,
  pace vs recovery scatter, upcoming sessions with completion status

---

## Explicitly out of scope (V0)

- Google Calendar write-back (rescheduling sessions)
- Weather API integration
- Webhook-based real-time sync (Strava/Whoop) — nightly batch is sufficient
- Vector store / semantic memory
- Push notifications / morning briefing
- Multi-user support
- Production hardening (rate limiting, auth middleware, etc.)

---

## Environment variables

All secrets live in `.env` (local) and Render environment variables (deployed). Never in code.
See `.env.example` for the full list. OAuth tokens for all three sources are stored as env vars
(single-user simplification — no token table needed).
