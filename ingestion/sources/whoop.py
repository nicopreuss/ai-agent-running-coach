"""Whoop data source: fetches, normalises, and upserts daily recovery data."""

import os
import time

import requests
from dotenv import load_dotenv

from ingestion.sources.base import DataSource

load_dotenv()

_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
_BASE_URL = "https://api.prod.whoop.com/developer/v2"


class WhoopSource(DataSource):
    """Fetches daily recovery, sleep, and cycle data from the Whoop API v2."""

    def __init__(self, start_date: str | None = None) -> None:
        """
        Args:
            start_date: ISO date string (YYYY-MM-DD) — only fetch records from this date onward.
                        Pass None to fetch full history (backfill).
        """
        self._client_id = os.environ["WHOOP_CLIENT_ID"]
        self._client_secret = os.environ["WHOOP_CLIENT_SECRET"]
        self._refresh_token = os.environ["WHOOP_REFRESH_TOKEN"]
        self._access_token = os.environ["WHOOP_ACCESS_TOKEN"]
        self._expires_at: float = 0  # force refresh on first call
        self._start_date = start_date

    # ── Token management ─────────────────────────────────────────────────────

    def _ensure_valid_token(self) -> str:
        if time.time() >= self._expires_at:
            self._do_token_refresh()
        return self._access_token

    def _do_token_refresh(self) -> None:
        response = requests.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": "read:recovery read:cycles read:sleep offline",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        self._access_token = data["access_token"]
        self._refresh_token = data["refresh_token"]
        self._expires_at = time.time() + data["expires_in"]

    def _get(self, path: str, params: dict | None = None) -> dict:
        """Authenticated GET against the Whoop v2 API."""
        response = requests.get(
            f"{_BASE_URL}{path}",
            headers={"Authorization": f"Bearer {self._ensure_valid_token()}"},
            params=params or {},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def _paginate(self, path: str, params: dict | None = None) -> list[dict]:
        """Fetch all pages from a cursor-paginated Whoop endpoint."""
        results = []
        next_token = None
        while True:
            page_params = {**(params or {}), "limit": 25}
            if next_token:
                page_params["nextToken"] = next_token
            data = self._get(path, page_params)
            results.extend(data.get("records", []))
            next_token = data.get("next_token")
            if not next_token:
                break
        return results

    # ── DataSource interface (stubs — filled in next step) ────────────────────

    def fetch(self) -> list[dict]:
        raise NotImplementedError

    def normalize(self, raw: list[dict]) -> list[dict]:
        raise NotImplementedError

    def upsert(self, records: list[dict]) -> int:
        raise NotImplementedError
