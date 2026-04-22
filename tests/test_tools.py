"""Tests for agent tools defined in agent/tools.py."""

from agent.tools import example_tool


def test_example_tool_returns_string() -> None:
    """example_tool should return a non-empty string for any string input."""
    result = example_tool.invoke("test input")
    assert isinstance(result, str)
    assert len(result) > 0


def test_example_tool_includes_query_in_output() -> None:
    """Placeholder: replace with a real assertion once example_tool is implemented."""
    # REPLACE: update this test to assert the actual expected output once
    # example_tool performs a real operation (DB query, API call, etc.)
    result = example_tool.invoke("my query")
    assert "my query" in result
