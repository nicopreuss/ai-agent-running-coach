# Ingestion Refresh Design

**Date:** 2026-05-03
**Status:** Approved

## Overview

Add ongoing data refresh to the running coach pipeline. Historical backfill is already complete. This design covers three trigger paths for keeping Whoop and Strava data current: a daily scheduled job, a manual UI button, and an agent-triggered tool call. All three paths funnel into the same `pipeline.run(source)` function.

---

## 1. Data Layer — `ingestion_log` table + watermark

**Model:** Add `IngestionLog` SQLAlchemy model to `db/models.py`.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| source | ENUM | whoop / strava |
| status | ENUM | success / partial / failed |
| records_fetched | INT | |
| records_inserted | INT | |
| records_skipped | INT | deduped |
| last_fetched_at | TIMESTAMPTZ | watermark for next run |
| error_message | TEXT | nullable |
| created_at | TIMESTAMPTZ | |

**Watermark logic in `pipeline.run(source)`:**

1. Query `ingestion_log` for the most recent `status=success` row for the given source → read `last_fetched_at`
2. Pass `since=last_fetched_at` to `source.fetch()` (both Strava and Whoop already support date-range parameters — wire them to the watermark)
3. On success: write new `ingestion_log` row with `status=success`, `last_fetched_at=now()`
4. On failure: write `status=failed`, `error_message=<exception>`, no watermark update — next run retries from the same point

This makes ingestion self-healing: if a daily job is missed, the next run catches up from the last successful watermark without duplicating data (upserts are idempotent).

---

## 2. FastAPI — Scheduler + On-Demand Endpoints

**Scheduler:** APScheduler initializes at FastAPI startup with two jobs:

| Job | Schedule | Timezone |
|---|---|---|
| `run_whoop_ingestion` | Daily 09:00 | Europe/Paris |
| `run_strava_ingestion` | Daily 20:00 | Europe/Paris |

Both jobs call `pipeline.run(source)` directly.

**New endpoints:**

- `POST /ingest/whoop` — triggers Whoop ingestion immediately
- `POST /ingest/strava` — triggers Strava ingestion immediately

Response shape:
```json
{"status": "ok", "source": "whoop", "records_inserted": 1}
```

Both endpoints run synchronously. At single-user scale, ingestion completes in seconds — no async job queue needed. Concurrent calls are safe because upserts are idempotent.

---

## 3. Agent Tool — `refresh_data`

New LangChain tool added alongside the existing three tools.

- **Input:** `source` — one of `"whoop"`, `"strava"`, or `"all"`
- **Action:** calls `POST /ingest/{source}` (or both endpoints if `"all"`)
- **Returns:** human-readable summary the agent cites in its response

Example outputs:
- `"Whoop data refreshed — 1 new record inserted."`
- `"Strava data refreshed — already up to date."`

Example agent interactions:
- "Make sure my data is fresh" → `refresh_data(source="all")`
- "Pull today's recovery score" → `refresh_data(source="whoop")` then answers

---

## 4. Streamlit UI — Refresh All Button

A single **"Refresh All"** button in the metrics dashboard panel:

1. On click: calls `POST /ingest/whoop` and `POST /ingest/strava` sequentially
2. Shows a spinner while running
3. On completion: displays `"Synced — N new records."` then reloads dashboard charts

---

## Files Affected

| File | Change |
|---|---|
| `db/models.py` | Add `IngestionLog` model |
| `ingestion/pipeline.py` | Add watermark read/write, pass `since` to sources |
| `ingestion/sources/strava.py` | Wire `since` parameter to API call |
| `ingestion/sources/whoop.py` | Wire `since` parameter to API call |
| `api/main.py` | Add APScheduler startup, `POST /ingest/whoop`, `POST /ingest/strava` |
| `agent/tools.py` | Add `refresh_data` tool |
| `ui/app.py` | Add "Refresh All" button |
