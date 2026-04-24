# Running Coach AI Agent

A personal AI running coach built for the DataExpert.io AI Engineer Bootcamp capstone. It ingests training and physiological data from Strava, Whoop, and Google Calendar into a unified Postgres schema, then exposes a LangChain ReAct agent that answers analytical questions about performance, recovery, and upcoming sessions — e.g. "How did my HRV affect my pace last month?" or "What's my training load this week compared to last?"

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

---

## Project structure

```
ai-agent-running-coach/
├── agent/
│   ├── agent.py        # ReAct agent setup and run() entrypoint
│   ├── tools.py        # @tool-decorated functions available to the agent
│   └── prompts.py      # System prompt and prompt templates
├── ingestion/
│   ├── pipeline.py     # Orchestrates fetch → normalize → upsert
│   └── sources/
│       ├── base.py     # Abstract DataSource base class
│       ├── strava.py   # Strava API v3 source
│       └── whoop.py    # Whoop API v2 source
├── db/
│   ├── client.py       # SQLAlchemy engine and get_connection()
│   └── models.py       # ORM model definitions
├── api/
│   └── main.py         # FastAPI app (GET /health, POST /chat)
├── scripts/
│   ├── create_tables.py              # One-time DB schema setup
│   ├── whoop_oauth.py                # One-time Whoop token acquisition
│   ├── smoke_test_strava_ingest.py   # Strava end-to-end smoke test
│   └── smoke_test_whoop_connection.py # Whoop connection smoke test
├── evals/
│   ├── run_evals.py    # Evaluation runner
│   └── golden_set.json # Ground-truth Q&A pairs
├── tests/
│   ├── test_agent.py
│   └── test_tools.py
├── .env.example        # All required env vars with comments
├── pyproject.toml      # Poetry project config and dependencies
└── main.py             # CLI entry point
```

---

## Running the agent

```bash
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
