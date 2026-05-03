"""Tests for agent tools defined in agent/tools.py."""

from agent.tools import get_tools, refresh_data


def test_get_tools_returns_list() -> None:
    """get_tools() should return a non-empty list."""
    tools = get_tools()
    assert isinstance(tools, list)
    assert len(tools) > 0


def test_get_tools_contains_refresh_data() -> None:
    """get_tools() should include the refresh_data tool."""
    tools = get_tools()
    assert refresh_data in tools
