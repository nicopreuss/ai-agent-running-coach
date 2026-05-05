"""Tests for the agent module."""

from unittest.mock import MagicMock, patch

import pytest

from agent.agent import build_agent, run


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
        result = run("refresh my data")

    assert result["response"] == "Your data is up to date."
    assert result["tools_used"] == ["refresh_data"]


def test_run_reraises_on_failure() -> None:
    """run() re-raises exceptions raised by the agent."""
    mock_agent = MagicMock()
    mock_agent.invoke.side_effect = RuntimeError("LLM unavailable")

    with patch("agent.agent._agent", mock_agent):
        with pytest.raises(RuntimeError, match="LLM unavailable"):
            run("failing query")


def test_build_agent_injects_athlete_context() -> None:
    """build_agent() prepends athlete context to the system prompt."""
    mock_context = "## Athlete Profile\nGoal: Paris Marathon sub-4h"
    captured_prompts = []

    def capture_create(llm, **kwargs):
        captured_prompts.append(kwargs["prompt"])
        return MagicMock()

    with patch("agent.agent.load_athlete_context", return_value=mock_context):
        with patch("agent.agent.ChatOpenAI"):
            with patch("agent.agent.MemorySaver"):
                with patch("agent.agent.create_react_agent", side_effect=capture_create):
                    build_agent()

    assert len(captured_prompts) == 1
    assert "Athlete Profile" in captured_prompts[0].content
    assert "sub-4h" in captured_prompts[0].content
