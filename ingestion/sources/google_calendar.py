"""Google Calendar data source: fetches and normalises Runna training sessions."""

import os
import re
import time
from datetime import date, datetime, timedelta, timezone

import requests

from ingestion.sources.base import DataSource

_RUNNA_URL_RE = re.compile(r"https://club\.runna\.com\S+")
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
_WINDOW_DAYS = 90


class GoogleCalendarSource(DataSource):
    """Fetches Runna training sessions from a Google Calendar."""

    def __init__(self) -> None:
        self._client_id = os.environ["GOOGLE_CLIENT_ID"]
        self._client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
        self._refresh_token = os.environ["GOOGLE_REFRESH_TOKEN"]
        self._calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
        self._access_token: str | None = None
        self._expires_at: float = 0

    def _do_token_refresh(self) -> None:
        response = requests.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": "https://www.googleapis.com/auth/calendar.readonly",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        self._access_token = data["access_token"]
        self._expires_at = time.time() + data["expires_in"]

    def _ensure_valid_token(self) -> str:
        if time.time() >= self._expires_at:
            self._do_token_refresh()
        return self._access_token  # type: ignore[return-value]

    def fetch(self) -> list[dict]:
        """Fetch all events in the rolling 90-day window from Google Calendar."""
        now = datetime.now(tz=timezone.utc)
        time_min = (now - timedelta(days=_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        time_max = (now + timedelta(days=_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")

        results = []
        page_token = None
        while True:
            params: dict = {
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 250,
            }
            if page_token:
                params["pageToken"] = page_token

            response = requests.get(
                f"{_CALENDAR_API_BASE}/calendars/{self._calendar_id}/events",
                headers={"Authorization": f"Bearer {self._ensure_valid_token()}"},
                params=params,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            results.extend(data.get("items", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return results

    def normalize(self, raw: list[dict]) -> list[dict]:
        """Filter to Runna events and map to the DB schema."""
        records = []
        for event in raw:
            description = event.get("description") or ""
            if "club.runna.com" not in description:
                continue

            match = _RUNNA_URL_RE.search(description)
            runna_url = match.group(0) if match else None

            start = event.get("start", {})
            event_date: date | None = None
            if "date" in start:
                event_date = date.fromisoformat(start["date"])
            elif "dateTime" in start:
                event_date = datetime.fromisoformat(start["dateTime"]).date()

            records.append({
                "google_event_id": event["id"],
                "date": event_date,
                "title": event.get("summary"),
                "description": description,
                "runna_url": runna_url,
            })
        return records

    def upsert(self, records: list[dict]) -> int:
        raise NotImplementedError
