"""Tests for the agent module."""

from unittest.mock import MagicMock, patch


def test_run_returns_response_dict() -> None:
    """agent.run() should return a dict with response and tools_used keys."""
    mock_executor = MagicMock()
    mock_executor.invoke.return_value = {"output": "test response", "intermediate_steps": []}

    with patch("agent.agent._agent", mock_executor):
        from agent.agent import run
        result = run("test query")

    assert result == {"response": "test response", "tools_used": []}
    mock_executor.invoke.assert_called_once_with({"input": "test query"})


def test_run_extracts_tool_names_from_intermediate_steps() -> None:
    """agent.run() should pull tool names from each AgentAction in intermediate_steps."""
    action_a = MagicMock()
    action_a.tool = "refresh_data"
    action_b = MagicMock()
    action_b.tool = "get_recent_stats"

    mock_executor = MagicMock()
    mock_executor.invoke.return_value = {
        "output": "Here is your summary.",
        "intermediate_steps": [
            (action_a, "Strava: already up to date."),
            (action_b, "You ran 3 times last week."),
        ],
    }

    with patch("agent.agent._agent", mock_executor):
        from agent.agent import run
        result = run("How was my week?")

    assert result["response"] == "Here is your summary."
    assert result["tools_used"] == ["refresh_data", "get_recent_stats"]


def test_run_reraises_on_failure() -> None:
    """agent.run() should re-raise exceptions raised by the executor."""
    import pytest

    mock_executor = MagicMock()
    mock_executor.invoke.side_effect = RuntimeError("LLM unavailable")

    with patch("agent.agent._agent", mock_executor):
        from agent.agent import run
        with pytest.raises(RuntimeError, match="LLM unavailable"):
            run("failing query")
