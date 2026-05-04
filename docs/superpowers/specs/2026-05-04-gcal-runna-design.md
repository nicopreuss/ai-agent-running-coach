# Google Calendar Runna Sessions Ingestion — Design Spec

## Goal

Ingest Runna training sessions from Google Calendar into a `google_calendar_runna_sessions`
Supabase table. The system fetches a rolling 90-day window (past and future), filters to Runna
events, and stores the raw event data (date, title, description, Runna URL) for use by the agent.

---

## Constraints

- **Read-only calendar access is non-negotiable.** The OAuth scope is hardcoded to
  `calendar.readonly`. No write endpoints are called anywhere in the implementation.
- Single calendar ID (`GOOGLE_CALENDAR_ID` env var) — no cross-calendar access.
- No LLM classification, no Strava linking, no session_type enum — raw data only (V0).
- Runna URL reading/scraping is explicitly out of scope for this implementation.

---

## Architecture

The Google Calendar source follows the existing `DataSource` pattern used by `WhoopSource` and
`StravaSource`.

### New file: `ingestion/sources/google_calendar.py`

`GoogleCalendarSource` implements `DataSource` with three methods:

**`fetch()`**
- Reads `GOOGLE_CALENDAR_ID`, `GOOGLE_REFRESH_TOKEN`, `GOOGLE_CLIENT_ID`,
  `GOOGLE_CLIENT_SECRET` from env.
- Exchanges the refresh token for an access token at `https://oauth2.googleapis.com/token`,
  requesting scope `calendar.readonly` only.
- Calls `GET https://www.googleapis.com/calendar/v3/calendars/{calendarId}/events` with:
  - `timeMin` = today − 90 days (RFC3339 UTC)
  - `timeMax` = today + 90 days (RFC3339 UTC)
  - `singleEvents=true`, `orderBy=startTime`
  - Cursor pagination via `pageToken`
- Returns all raw event dicts from the API response.

**`normalize(raw)`**
- Filters events whose `description` field contains `club.runna.com` — events without this
  string are silently skipped (not Runna events).
- Extracts the Runna URL using regex `https://club\.runna\.com\S+` from the description.
- Maps to DB schema: `google_event_id`, `date`, `title`, `description`, `runna_url`.
- `date` is derived from `start.date` (all-day events) or `start.dateTime` (timed events).
- Returns list of normalised dicts.

**`upsert(records)`**
- `INSERT INTO google_calendar_runna_sessions ... ON CONFLICT (google_event_id) DO NOTHING`
- Returns `rowcount` (number of new rows inserted).
- Because the primary key is `google_event_id`, re-fetching the full window is idempotent.

### Pipeline integration

`pipeline.run("google_calendar")` adds a branch to the existing `if/elif` block:
- No watermark is used — full rolling window on every run.
- Writes success/failure to `ingestion_log` with `source = "google_calendar"`.

### Scheduler

A third `CronTrigger` job in `api/main.py` lifespan, running daily at **noon Europe/Paris**.

### API endpoint

`POST /ingest/google_calendar` — same shape as `/ingest/whoop` and `/ingest/strava`.
Returns `IngestResponse(status="ok", source="google_calendar", records_inserted=N)`.

### Streamlit "Refresh All"

Updated to call `/ingest/google_calendar` alongside Whoop and Strava. Total count includes
Google Calendar records inserted.

### Agent `refresh_data` tool

`source="all"` updated to loop over `["whoop", "strava", "google_calendar"]`.

---

## Data Model

### Table: `google_calendar_runna_sessions`

| Column | Type | Notes |
|---|---|---|
| `google_event_id` | TEXT PK | Stable Google Calendar event ID — dedup key |
| `date` | DATE | Session date (from event start) |
| `title` | TEXT | Raw event `summary` field |
| `description` | TEXT | Full raw event description |
| `runna_url` | TEXT | Extracted `club.runna.com` URL |
| `created_at` | TIMESTAMPTZ | `server_default=now()` |

### SQLAlchemy model: `GoogleCalendarRunnaSession`

Added to `db/models.py` following the existing `Mapped`/`mapped_column` pattern.

---

## Auth and Read-Only Guardrails

1. **Scope hardcoded to `calendar.readonly`** in the token refresh POST body. The access token
   issued is scoped to what we request, enforced by Google's OAuth server.
2. **Only `events.list` (GET) is ever called.** No POST, PATCH, PUT, or DELETE calls exist in
   the implementation.
3. **Single calendar**: `GOOGLE_CALENDAR_ID` targets one specific calendar. The code never
   lists calendars or touches any other calendar.
4. **Tests verify**: the token refresh request carries `calendar.readonly` scope, and no write
   HTTP method is called.

---

## Environment Variables

These already exist in `.env.example`:

```
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=
GOOGLE_CALENDAR_ID=
```

No new env vars required.

---

## Dependencies

No new dependencies. `requests` is already installed.

---

## Error Handling

- Token refresh failure → `requests.raise_for_status()` → exception propagates to
  `pipeline.run()` → logged to `ingestion_log` as `failed`, re-raised.
- Calendar API error → same propagation path.
- Events with no description or no Runna URL are silently skipped in `normalize()`.
- Events with no start date are silently skipped.

---

## Testing

| Test file | What it covers |
|---|---|
| `tests/test_gcal_source.py` | `normalize()` filters non-Runna events, extracts URL, maps date correctly; empty input returns empty list |
| `tests/test_gcal_source.py` | `normalize()` handles all-day (`start.date`) and timed (`start.dateTime`) events |
| `tests/test_gcal_auth.py` | Token refresh sends `calendar.readonly` scope; access token is used in the `events.list` request |
| `tests/test_ingest_endpoints.py` | `POST /ingest/google_calendar` returns 200 with correct shape; returns 500 on pipeline failure |

All tests use `unittest.mock.patch` — no real API calls.

---

## Out of Scope (V0)

- Runna URL fetching / page scraping
- LLM-based session type classification
- Linking to Strava activities (`completed` flag)
- Detecting deleted calendar events
- Writing back to Google Calendar
