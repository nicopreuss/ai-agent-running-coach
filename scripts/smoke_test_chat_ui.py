"""Smoke test: verify the /chat endpoint returns a response and tools_used list."""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

_API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


def main() -> None:
    query = "Say hello and tell me what tools you have available."
    print(f"Sending query: {query!r}")

    resp = requests.post(f"{_API_BASE_URL}/chat", json={"query": query}, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    assert "response" in data, "Missing 'response' field in API response"
    assert isinstance(data["response"], str), "'response' must be a string"
    assert "tools_used" in data, "Missing 'tools_used' field in API response"
    assert isinstance(data["tools_used"], list), "'tools_used' must be a list"

    print(f"\nResponse  : {data['response']}")
    print(f"Tools used: {data['tools_used'] or '(none)'}")
    print("\nSmoke test passed.")


if __name__ == "__main__":
    main()
