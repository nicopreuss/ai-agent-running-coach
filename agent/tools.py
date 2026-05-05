"""Tool definitions for the LangChain agent."""

import os

import requests
from langchain_core.tools import tool

from agent.memory import add_session_note as _add_session_note
from agent.memory import update_athlete_profile as _update_athlete_profile

_API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

_SOURCE_LABELS = {
    "whoop": "Whoop",
    "strava": "Strava",
    "google_calendar": "Google Calendar",
}


@tool
def refresh_data(source: str) -> str:
    """Fetch the latest data from Whoop, Strava, and/or Google Calendar and update the database.

    Use this tool when the user asks to refresh data, check if data is fresh,
    or explicitly requests pulling the latest recovery, activity, or training session records.

    Args:
        source: Which source to refresh — "whoop", "strava", "google_calendar", or "all".

    Returns:
        A plain-English summary of how many records were inserted.
    """
    sources = ["whoop", "strava", "google_calendar"] if source == "all" else [source]
    summaries = []

    for s in sources:
        response = requests.post(f"{_API_BASE_URL}/ingest/{s}", timeout=60)
        response.raise_for_status()
        data = response.json()
        n = data["records_inserted"]
        label = _SOURCE_LABELS.get(s, s.capitalize())
        if n == 0:
            summaries.append(f"{label}: already up to date.")
        elif n == 1:
            summaries.append(f"{label}: 1 new record inserted.")
        else:
            summaries.append(f"{label}: {n} new records inserted.")

    return " ".join(summaries)


@tool
def update_athlete_profile(fact: str) -> str:
    """Save a permanent fact to the athlete's profile.

    Call when the athlete explicitly says "remember that..." or asks you to save
    something to their profile. The fact is timestamped and appended.

    Args:
        fact: The fact or piece of information to save permanently.

    Returns:
        Confirmation that the fact was saved.
    """
    return _update_athlete_profile(fact)


@tool
def add_session_note(note: str) -> str:
    """Record a noteworthy observation from the current session.

    Call proactively when the athlete mentions something useful for future
    conversations: training feelings, fatigue, injuries, goal hints, or any
    relevant observation. The note is timestamped and appended to today's log.

    Args:
        note: The observation to record.

    Returns:
        Confirmation that the note was saved.
    """
    return _add_session_note(note)


def get_tools() -> list:
    """Return the list of tools registered with the agent."""
    return [refresh_data, update_athlete_profile, add_session_note]
