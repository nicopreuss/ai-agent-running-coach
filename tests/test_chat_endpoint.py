"""Tests for the /chat endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


def test_chat_returns_response_and_tools_used() -> None:
    """/chat should return response text and a list of tool names."""
    mock_result = {
        "response": "You ran 3 times last week.",
        "tools_used": ["get_training_and_recovery"],
    }

    with patch("api.main.agent_module.run", return_value=mock_result):
        with TestClient(app) as client:
            response = client.post("/chat", json={"query": "How was my week?"})

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "You ran 3 times last week."
    assert data["tools_used"] == ["get_training_and_recovery"]


def test_chat_returns_empty_tools_when_none_used() -> None:
    """/chat should return an empty tools_used list when the agent uses no tools."""
    mock_result = {"response": "Sure, I can help with that.", "tools_used": []}

    with patch("api.main.agent_module.run", return_value=mock_result):
        with TestClient(app) as client:
            response = client.post("/chat", json={"query": "Hello"})

    assert response.status_code == 200
    data = response.json()
    assert data["tools_used"] == []
