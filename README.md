# Running Coach AI Agent

A personal AI running coach built for the DataExpert.io AI Engineer Bootcamp capstone. It ingests training and physiological data from Strava, Whoop, and Google Calendar into a unified Postgres schema, then exposes a LangGraph agent that answers analytical questions about performance, recovery, and upcoming sessions — e.g. "How did my HRV affect my pace last month?" or "What's my training load this week compared to last?"

---

## Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)
- A [Supabase](https://supabase.com) project (free tier works)
- Strava and Whoop developer app credentials (see **Data source setup** below)

---

## Setup

```bash
git clone <repo-url>
cd ai-agent-running-coach

# Install dependencies
poetry install

# Configure environment
cp .env.example .env
# Fill in all values in .env (see Data source setup below)

# Create database tables (run once)
poetry run python -m scripts.create_tables

# Run the full Strava ingest
poetry run python -m scripts.smoke_test_strava_ingest

# Start the agent
poetry run python main.py
```

---

## Data source setup

### Supabase (database)

1. Create a free project at [supabase.com](https://supabase.com).
2. Go to **Project Settings → Database → Connection String → URI** and copy the direct connection string (port 5432, not 6543).
3. Add it to `.env` as `DATABASE_URL`.
4. Run the table creation script once: `poetry run python -m scripts.create_tables`

### Strava

1. Go to [strava.com/settings/api](https://www.strava.com/settings/api) and create an app.
   Set **Authorization Callback Domain** to `localhost`.
2. Copy **Client ID** and **Client Secret** into `.env`.
3. Perform the one-time OAuth flow to get your tokens:
   - Open this URL in your browser (replace `YOUR_CLIENT_ID`):
     ```
     https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=activity:read_all
     ```
   - Authorise → your browser redirects to `http://localhost/exchange_token?code=XXXX`
   - Copy the `code` value, then exchange it for tokens:
     ```bash
     curl -X POST https://www.strava.com/oauth/token \
       -d client_id=YOUR_CLIENT_ID \
       -d client_secret=YOUR_CLIENT_SECRET \
       -d code=XXXX \
       -d grant_type=authorization_code
     ```
   - Copy `access_token` and `refresh_token` from the JSON response into `.env`.

### Whoop

1. Go to [developer.whoop.com](https://developer.whoop.com) and create an app.
   - Set the redirect URI to any HTTPS URL you control (e.g. your GitHub repo URL).
   - Whoop does not accept `localhost` or `127.0.0.1` as redirect URIs.
2. Copy **Client ID** and **Client Secret** into `.env`.
3. Set `WHOOP_REDIRECT_URI` in `.env` to the exact redirect URI you registered above.
4. Run the one-time OAuth helper:
   ```bash
   poetry run python -m scripts.whoop_oauth
   ```
   - Your browser opens the Whoop authorisation page.
   - After authorising, your browser redirects to your redirect URI with `?code=XXXX` in the address bar.
   - Copy the `code` value and paste it into the terminal when prompted.
   - The script prints `WHOOP_ACCESS_TOKEN` and `WHOOP_REFRESH_TOKEN` — paste them into `.env`.

### Google Calendar

1. In Google Calendar, open the Runna calendar → **Settings → Integrate calendar** and copy the Calendar ID.
2. Add `GOOGLE_CALENDAR_ID` to `.env`.
3. Run the one-time OAuth helper:
   ```bash
   poetry run python -m scripts.google_oauth
   ```
   - Your browser opens the Google consent screen; grant read-only access.
   - The script prints `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN` — paste them into `.env`.

---

## Project structure

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

---

## Running the app

```bash
# Start the API server
poetry run uvicorn api.main:app --reload

# Start the Streamlit UI (in a second terminal)
poetry run streamlit run ui/app.py

# Or: run the agent interactively from the terminal
poetry run python main.py
```

---

## Running evals

```bash
poetry run python evals/run_evals.py
```

Edit `evals/golden_set.json` to add question/expected_answer pairs. The runner prints PASS/FAIL per entry and exits with code 1 if any eval fails.

---

## Deploying to Render

In your Render service settings:

| Setting | Value |
|---|---|
| **Build command** | `pip install poetry && poetry install --without dev` |
| **Start command** | `poetry run uvicorn api.main:app --host 0.0.0.0 --port $PORT` |

Set all environment variables from `.env.example` in the Render dashboard under **Environment**.
