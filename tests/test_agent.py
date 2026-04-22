"""Tests for the agent module."""

from unittest.mock import MagicMock, patch


def test_run_returns_string() -> None:
    """agent.run() should return the output string from the AgentExecutor."""
    mock_executor = MagicMock()
    mock_executor.invoke.return_value = {"output": "test response"}

    with patch("agent.agent._agent", mock_executor):
        from agent.agent import run
        result = run("test query")

    assert result == "test response"
    mock_executor.invoke.assert_called_once_with({"input": "test query"})


def test_run_reraises_on_failure() -> None:
    """agent.run() should re-raise exceptions raised by the executor."""
    import pytest

    mock_executor = MagicMock()
    mock_executor.invoke.side_effect = RuntimeError("LLM unavailable")

    with patch("agent.agent._agent", mock_executor):
        from agent.agent import run
        with pytest.raises(RuntimeError, match="LLM unavailable"):
            run("failing query")
