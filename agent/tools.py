"""Tool definitions for the LangChain agent."""

import os

import requests
from langchain_core.tools import tool

_API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


@tool
def refresh_data(source: str) -> str:
    """Fetch the latest data from Whoop and/or Strava and update the database.

    Use this tool when the user asks to refresh data, check if data is fresh,
    or explicitly requests pulling the latest recovery or activity records.

    Args:
        source: Which source to refresh — "whoop", "strava", or "all".

    Returns:
        A plain-English summary of how many records were inserted.
    """
    sources = ["whoop", "strava"] if source == "all" else [source]
    summaries = []

    for s in sources:
        response = requests.post(f"{_API_BASE_URL}/ingest/{s}", timeout=60)
        response.raise_for_status()
        data = response.json()
        n = data["records_inserted"]
        label = s.capitalize()
        if n == 0:
            summaries.append(f"{label}: already up to date.")
        elif n == 1:
            summaries.append(f"{label}: 1 new record inserted.")
        else:
            summaries.append(f"{label}: {n} new records inserted.")

    return " ".join(summaries)


def get_tools() -> list:
    """Return the list of tools registered with the agent."""
    return [refresh_data]
