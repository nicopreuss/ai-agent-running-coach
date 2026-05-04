# LangGraph Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old LangChain `AgentExecutor` + text-based ReAct agent with `langgraph.prebuilt.create_react_agent`, fix the proxy session header, and add conversational memory via `MemorySaver`.

**Architecture:** `agent/agent.py` is fully rewritten — `build_agent()` and `run()` switch to LangGraph's message-based API. `tests/test_agent.py` is rewritten to mock LangGraph's return format. All other files (`api/main.py`, `ui/app.py`, `agent/tools.py`, `agent/prompts.py`, `tests/test_chat_endpoint.py`) are untouched. The public `run()` contract is unchanged: accepts `str`, returns `{"response": str, "tools_used": list[str]}`.

**Tech Stack:** `langgraph` (new), `langchain-core`, `langchain-openai`, `pytest`, `unittest.mock`

---

### Task 1: Add langgraph dependency

**Files:**
- Modify: `pyproject.toml`
- Modify: `poetry.lock` (auto-updated by poetry)

- [ ] **Step 1: Install langgraph via poetry**

Run:
```bash
poetry add langgraph
```

Expected: poetry resolves and installs `langgraph` and updates `pyproject.toml` and `poetry.lock`.

- [ ] **Step 2: Verify the import works**

Run:
```bash
poetry run python -c "from langgraph.prebuilt import create_react_agent; from langgraph.checkpoint.memory import MemorySaver; print('ok')"
```

Expected output:
```
ok
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml poetry.lock
git commit -m "chore: add langgraph dependency"
```

---

### Task 2: Migrate agent to LangGraph (TDD)

**Files:**
- Modify: `tests/test_agent.py` (rewrite all three tests)
- Modify: `agent/agent.py` (rewrite `build_agent()`, `run()`, remove `_REACT_TEMPLATE`)

- [ ] **Step 1: Rewrite `tests/test_agent.py` with failing tests**

Replace the entire file with:

```python
"""Tests for the agent module."""

from unittest.mock import MagicMock, patch

import pytest


def _make_ai_msg(content: str, tool_calls: list | None = None) -> MagicMock:
    msg = MagicMock()
    msg.type = "ai"
    msg.content = content
    msg.tool_calls = tool_calls or []
    return msg


def _make_tool_msg(content: str) -> MagicMock:
    msg = MagicMock()
    msg.type = "tool"
    msg.content = content
    msg.tool_calls = []
    return msg


def test_run_returns_response_and_empty_tools_used() -> None:
    """run() returns response text and empty tools_used when no tools are called."""
    mock_agent = MagicMock()
    mock_agent.invoke.return_value = {
        "messages": [_make_ai_msg("Hello! How can I help?")]
    }

    with patch("agent.agent._agent", mock_agent):
        from agent.agent import run
        result = run("hello")

    assert result == {"response": "Hello! How can I help?", "tools_used": []}
    mock_agent.invoke.assert_called_once()


def test_run_extracts_tool_names_from_tool_calls() -> None:
    """run() reads tool names from tool_calls on AI messages."""
    ai_with_tool = _make_ai_msg(
        content="",
        tool_calls=[{"name": "refresh_data", "args": {"source": "all"}, "id": "call_1"}],
    )
    tool_result = _make_tool_msg("Strava: already up to date.")
    ai_final = _make_ai_msg("Your data is up to date.")

    mock_agent = MagicMock()
    mock_agent.invoke.return_value = {
        "messages": [ai_with_tool, tool_result, ai_final]
    }

    with patch("agent.agent._agent", mock_agent):
        from agent.agent import run
        result = run("refresh my data")

    assert result["response"] == "Your data is up to date."
    assert result["tools_used"] == ["refresh_data"]


def test_run_reraises_on_failure() -> None:
    """run() re-raises exceptions raised by the agent."""
    mock_agent = MagicMock()
    mock_agent.invoke.side_effect = RuntimeError("LLM unavailable")

    with patch("agent.agent._agent", mock_agent):
        from agent.agent import run
        with pytest.raises(RuntimeError, match="LLM unavailable"):
            run("failing query")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
poetry run pytest tests/test_agent.py -v
```

Expected: all 3 tests **FAIL**. The first two fail because `run()` still returns `result["output"]` (key doesn't exist in LangGraph format); the third may pass or fail depending on mock. Any failure confirms the tests are exercising real code.

- [ ] **Step 3: Rewrite `agent/agent.py`**

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

from agent.prompts import SYSTEM_PROMPT
from agent.tools import get_tools

load_dotenv()

logger = logging.getLogger(__name__)

_SESSION_ID = str(uuid4())
_THREAD = {"configurable": {"thread_id": _SESSION_ID}}


def build_agent():
    """Instantiate and return the LangGraph ReAct agent with memory."""
    llm = ChatOpenAI(
        model=os.environ["OPENAI_MODEL"],
        temperature=0,
        default_headers={"X-Session-ID": _SESSION_ID},
    )
    checkpointer = MemorySaver()
    return create_react_agent(
        llm,
        tools=get_tools(),
        prompt=SystemMessage(content=SYSTEM_PROMPT),
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
            if hasattr(msg, "tool_calls")
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

- [ ] **Step 4: Run the full test suite**

Run:
```bash
poetry run pytest -q
```

Expected: all tests pass. Confirm `tests/test_agent.py` shows 3 passed and `tests/test_chat_endpoint.py` shows 2 passed.

- [ ] **Step 5: Commit**

```bash
git add agent/agent.py tests/test_agent.py
git commit -m "feat: migrate agent to LangGraph with MemorySaver and correct session header"
```
