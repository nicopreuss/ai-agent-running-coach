"""Google Calendar data source: fetches and normalises Runna training sessions."""

import os
import re
from datetime import date, datetime

from ingestion.sources.base import DataSource

_RUNNA_URL_RE = re.compile(r"https://club\.runna\.com\S+")


class GoogleCalendarSource(DataSource):
    """Fetches Runna training sessions from a Google Calendar."""

    def __init__(self) -> None:
        self._client_id = os.environ["GOOGLE_CLIENT_ID"]
        self._client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
        self._refresh_token = os.environ["GOOGLE_REFRESH_TOKEN"]
        self._calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
        self._access_token: str | None = None
        self._expires_at: float = 0

    def fetch(self) -> list[dict]:
        raise NotImplementedError

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
