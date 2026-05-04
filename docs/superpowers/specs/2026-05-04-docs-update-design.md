# Docs Update Design

## Goal

Bring CLAUDE.md and README.md up to date with the current project state after the LangGraph migration, Google Calendar ingestion, dashboard metrics, and chat UI features.

## Scope

Targeted fixes only — edit stale content, add missing content. No restructuring.

## Changes

### CLAUDE.md

**Tech stack table** (one line):
- Change: `LangChain (ReAct agent)` → `LangGraph (create_react_agent + MemorySaver)`

### README.md

**1. Intro paragraph**
- Change: "exposes a LangChain ReAct agent" → "exposes a LangGraph agent"

**2. Project structure tree**
Replace the current tree with an updated one that includes:
- `ui/app.py` — Streamlit two-panel app (missing entirely)
- `api/dashboard.py` — dashboard data endpoints
- Full `tests/` list: `test_agent.py`, `test_chat_endpoint.py`, `test_dashboard_endpoint.py`, `test_gcal_model.py`, `test_gcal_source.py`, `test_ingest_endpoints.py`, `test_ingestion_log_model.py`, `test_pipeline.py`, `test_refresh_tool.py`, `test_tools.py`, `test_whoop_normalize.py`
- Full `scripts/` list: add `google_oauth.py`, `seed_ingestion_log.py`, `smoke_test_chat_ui.py`, `smoke_test_gcal_ingest.py`, `smoke_test_whoop_ingest.py`
- `ingestion/sources/google_calendar.py`

**3. Running the app**
Replace the single `poetry run python main.py` section with three options:
```bash
# Start the API server
poetry run uvicorn api.main:app --reload

# Start the Streamlit UI (in a second terminal)
poetry run streamlit run ui/app.py

# Or: run the agent interactively from the terminal
poetry run python main.py
```

**4. Google Calendar setup** (new subsection under "Data source setup")
After the Whoop section, add:

**Google Calendar**
1. In Google Calendar, open the Runna calendar → **Settings → Integrate calendar** and copy the Calendar ID.
2. Add `GOOGLE_CALENDAR_ID` to `.env`.
3. Run the one-time OAuth helper:
   ```bash
   poetry run python -m scripts.google_oauth
   ```
   - Your browser opens the Google consent screen; grant read-only access.
   - The script prints `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN` — paste them into `.env`.

## Out of Scope

- Full README rewrite (deferred until pre-submission)
- Adding architecture diagrams or badges
- Any changes to `.env.example` (already up to date)
