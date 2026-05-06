"""Tool definitions for the LangChain agent."""

import os

import requests
from langchain_core.tools import tool

from agent.memory import add_session_note as _add_session_note
from agent.memory import update_athlete_profile as _update_athlete_profile
from agent.queries import get_training_and_recovery as _get_training_and_recovery
from agent.queries import get_upcoming_sessions as _get_upcoming_sessions
from db.client import get_connection

_API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

_SOURCE_LABELS = {
    "whoop": "Whoop",
    "strava": "Strava",
    "google_calendar": "Google Calendar",
}


@tool
def get_training_and_recovery(lookback_days: int = 7) -> str:
    """Use for ANY question about recent training or recovery — including runs (distance,
    pace, heart rate, efficiency factor), Whoop recovery scores, HRV, resting heart rate,
    sleep performance or duration, daily strain, or the relationship between any of these.
    Use it even when the question is only about runs or only about recovery.

    Args:
        lookback_days: How many days back to fetch. Default is 7. Increase for longer
            trend questions. Maximum is 90 days.

    Returns:
        Formatted text with one block per day showing recovery metrics and run details.
    """
    with get_connection() as conn:
        return _get_training_and_recovery(conn, lookback_days)


@tool
def get_upcoming_sessions(days_ahead: int = 7) -> str:
    """Use for ANY question about upcoming training sessions — next session, weekly
    training overview, what is planned on a specific date, or how many sessions are
    coming up. Default window is 7 days; increase days_ahead for a longer planning
    horizon (max 90 days).

    Args:
        days_ahead: How many days forward to look. Default is 7. Maximum is 90 days.

    Returns:
        Formatted text with one block per session showing date, title, and description.
    """
    with get_connection() as conn:
        return _get_upcoming_sessions(conn, days_ahead)


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
    return [
        get_training_and_recovery,
        get_upcoming_sessions,
        refresh_data,
        update_athlete_profile,
        add_session_note,
    ]
