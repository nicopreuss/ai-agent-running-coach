# project_name

REPLACE THIS PARAGRAPH with a one-paragraph overview of what this agent does, what data sources it connects to, and what questions it is designed to answer. Explain the problem it solves and who it is for.

---

## Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)
- A running Postgres or Supabase instance
- API keys for your LLM provider and any data sources (see `.env.example`)

---

## Setup

```bash
git clone <repo-url>
cd project_name

# Install dependencies
poetry install

# Configure environment
cp .env.example .env
# Fill in all values in .env before continuing

# Start the agent REPL
poetry run python main.py
```

---

## Project structure

```
project_name/
├── agent/
│   ├── agent.py        # ReAct agent setup and run() entrypoint
│   ├── tools.py        # @tool-decorated functions available to the agent
│   └── prompts.py      # System prompt and any prompt templates
├── ingestion/
│   ├── pipeline.py     # Orchestrates fetch → normalize → upsert
│   └── sources/
│       └── base.py     # Abstract DataSource base class
├── db/
│   ├── client.py       # SQLAlchemy engine and get_connection()
│   └── models.py       # ORM model definitions
├── api/
│   └── main.py         # FastAPI app (GET /health, POST /chat)
├── evals/
│   ├── run_evals.py    # Evaluation runner against golden_set.json
│   └── golden_set.json # Ground-truth Q&A pairs for regression testing
├── tests/
│   ├── test_agent.py   # Unit tests for the agent module
│   └── test_tools.py   # Unit tests for individual tools
├── .github/
│   └── workflows/
│       └── ci.yml      # GitHub Actions: test, lint, secret scan
├── .env.example        # All required env vars with comments
├── pyproject.toml      # Poetry project config and dependencies
└── main.py             # CLI entry point
```

---

## Running the agent

```bash
# Interactive REPL
poetry run python main.py
```

---

## Running evals

```bash
poetry run python evals/run_evals.py
```

Edit `evals/golden_set.json` to add question/expected_answer pairs. The runner prints PASS/FAIL per entry and exits with code 1 if any eval fails.

---

## Adding a new tool

1. **Define the tool** in `agent/tools.py` using the `@tool` decorator. Write a precise docstring — the LLM uses it to decide when to call the tool.

   ```python
   @tool
   def my_new_tool(query: str) -> str:
       """Use this tool when ... It returns ..."""
       # your implementation
       return result
   ```

2. **Register the tool** by adding it to the list returned by `get_tools()` in `agent/tools.py`:

   ```python
   def get_tools() -> list:
       return [example_tool, my_new_tool]
   ```

3. **Add a test** in `tests/test_tools.py` that calls `my_new_tool.invoke(...)` and asserts the expected output.

---

## Deploying to Render

In your Render service settings:

| Setting | Value |
|---|---|
| **Build command** | `pip install poetry && poetry install --without dev` |
| **Start command** | `poetry run uvicorn api.main:app --host 0.0.0.0 --port $PORT` |

Set all environment variables from `.env.example` in the Render dashboard under **Environment**.
