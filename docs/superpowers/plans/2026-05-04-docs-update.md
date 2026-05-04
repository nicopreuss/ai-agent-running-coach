# Docs Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring CLAUDE.md and README.md up to date with the current project state (LangGraph migration, Google Calendar ingestion, dashboard, chat UI).

**Architecture:** Two files modified with targeted edits — no restructuring, no new files. CLAUDE.md gets one line changed. README.md gets four sections updated: intro, project structure tree, running-the-app instructions, and a new Google Calendar setup subsection.

**Tech Stack:** Markdown only.

---

### Task 1: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Edit the tech stack line**

In `CLAUDE.md`, find the tech stack table row:

```
| Agent framework | LangChain (ReAct agent) |
```

Replace with:

```
| Agent framework | LangGraph (create_react_agent + MemorySaver) |
```

- [ ] **Step 2: Verify the change**

Run:
```bash
git diff CLAUDE.md
```

Expected: one line changed in the tech stack table, nothing else.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update agent framework in tech stack table to LangGraph"
```

---

### Task 2: Update README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Fix the intro paragraph**

In `README.md` line 3, find:

```
then exposes a LangChain ReAct agent that answers analytical questions
```

Replace with:

```
then exposes a LangGraph agent that answers analytical questions
```

- [ ] **Step 2: Replace the project structure tree**

Find the entire `## Project structure` fenced code block (lines 91–122 in the current file) and replace it with:

```
```
ai-agent-running-coach/
├── agent/
│   ├── agent.py        # LangGraph ReAct agent setup and run() entrypoint
│   ├── prompts.py      # System prompt
│   └── tools.py        # @tool-decorated functions available to the agent
├── api/
│   ├── dashboard.py    # Dashboard data endpoints
│   └── main.py         # FastAPI app (GET /health, POST /chat, dashboard routes)
├── db/
│   ├── client.py       # SQLAlchemy engine and get_connection()
│   └── models.py       # ORM model definitions
├── ingestion/
│   ├── pipeline.py     # Orchestrates fetch → normalize → upsert
│   └── sources/
│       ├── base.py             # Abstract DataSource base class
│       ├── google_calendar.py  # Google Calendar API source
│       ├── strava.py           # Strava API v3 source
│       └── whoop.py            # Whoop API v2 source
├── ui/
│   └── app.py          # Streamlit two-panel app (chat + metrics dashboard)
├── scripts/
│   ├── create_tables.py                # One-time DB schema setup
│   ├── google_oauth.py                 # One-time Google Calendar token acquisition
│   ├── seed_ingestion_log.py           # Seed ingestion log watermarks
│   ├── smoke_test_chat_ui.py           # Chat UI endpoint smoke test
│   ├── smoke_test_connection_db.py     # DB connection smoke test
│   ├── smoke_test_gcal_ingest.py       # Google Calendar end-to-end smoke test
│   ├── smoke_test_strava.py            # Strava connection smoke test
│   ├── smoke_test_strava_ingest.py     # Strava end-to-end smoke test
│   ├── smoke_test_whoop_connection.py  # Whoop connection smoke test
│   ├── smoke_test_whoop_ingest.py      # Whoop end-to-end smoke test
│   └── whoop_oauth.py                  # One-time Whoop token acquisition
├── evals/
│   ├── run_evals.py    # Evaluation runner
│   └── golden_set.json # Ground-truth Q&A pairs
├── tests/
│   ├── test_agent.py
│   ├── test_chat_endpoint.py
│   ├── test_dashboard_endpoint.py
│   ├── test_gcal_model.py
│   ├── test_gcal_source.py
│   ├── test_ingest_endpoints.py
│   ├── test_ingestion_log_model.py
│   ├── test_pipeline.py
│   ├── test_refresh_tool.py
│   ├── test_tools.py
│   └── test_whoop_normalize.py
├── .env.example        # All required env vars with comments
├── main.py             # CLI entry point (interactive terminal REPL)
└── pyproject.toml      # Poetry project config and dependencies
```
```

- [ ] **Step 3: Replace the "Running the agent" section**

Find:

```markdown
## Running the agent

```bash
poetry run python main.py
```
```

Replace with:

```markdown
## Running the app

```bash
# Start the API server
poetry run uvicorn api.main:app --reload

# Start the Streamlit UI (in a second terminal)
poetry run streamlit run ui/app.py

# Or: run the agent interactively from the terminal
poetry run python main.py
```
```

- [ ] **Step 4: Add Google Calendar setup subsection**

Find the end of the Whoop section (the line ending `---` after the Whoop instructions, before the `## Project structure` heading). Insert the following block between the Whoop section and that `---` divider:

```markdown
### Google Calendar

1. In Google Calendar, open the Runna calendar → **Settings → Integrate calendar** and copy the Calendar ID.
2. Add `GOOGLE_CALENDAR_ID` to `.env`.
3. Run the one-time OAuth helper:
   ```bash
   poetry run python -m scripts.google_oauth
   ```
   - Your browser opens the Google consent screen; grant read-only access.
   - The script prints `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN` — paste them into `.env`.

```

- [ ] **Step 5: Verify the changes**

Run:
```bash
git diff README.md
```

Check:
1. Intro paragraph: "LangGraph agent" (not LangChain)
2. Project structure: `ui/`, `api/dashboard.py`, 11 test files, 11 scripts, `google_calendar.py` all present
3. Running section: three commands shown, heading says "Running the app"
4. Google Calendar subsection appears between Whoop and the `---` divider before Project structure

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: update README for LangGraph, full project structure, GCal setup, and run instructions"
```
