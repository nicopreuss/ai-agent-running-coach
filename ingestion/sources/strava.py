"""Strava data source: fetches, normalises, and upserts running activities."""

import os
import time
import uuid
from datetime import datetime

import requests
from dotenv import load_dotenv
from sqlalchemy.dialects.postgresql import insert

from db.client import get_connection
from db.models import Activity
from ingestion.sources.base import DataSource

load_dotenv()

_TOKEN_URL = "https://www.strava.com/oauth/token"
_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"


class StravaSource(DataSource):
    """Fetches completed running activities from the Strava API v3."""

    def __init__(self, after_timestamp: int | None = None) -> None:
        """
        Args:
            after_timestamp: Unix epoch — only fetch activities after this time.
                             Pass None to fetch full history (backfill).
        """
        self._client_id = os.environ["STRAVA_CLIENT_ID"]
        self._client_secret = os.environ["STRAVA_CLIENT_SECRET"]
        self._refresh_token = os.environ["STRAVA_REFRESH_TOKEN"]
        self._access_token = os.environ["STRAVA_ACCESS_TOKEN"]
        self._expires_at: float = 0  # force refresh on first call
        self._after_timestamp = after_timestamp

    # ── Token management ─────────────────────────────────────────────────────

    def _ensure_valid_token(self) -> str:
        if time.time() >= self._expires_at:
            self._do_token_refresh()
        return self._access_token

    def _do_token_refresh(self) -> None:
        response = requests.post(
            _TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        self._access_token = data["access_token"]
        self._refresh_token = data["refresh_token"]  # Strava rotates refresh tokens on use
        self._expires_at = data["expires_at"]

    # ── DataSource interface ──────────────────────────────────────────────────

    def fetch(self) -> list[dict]:
        """Fetch all running activities from Strava, paginating until exhausted."""
        activities: list[dict] = []
        page = 1

        while True:
            params: dict = {"per_page": 200, "page": page}
            if self._after_timestamp:
                params["after"] = self._after_timestamp

            response = requests.get(
                _ACTIVITIES_URL,
                headers={"Authorization": f"Bearer {self._ensure_valid_token()}"},
                params=params,
                timeout=10,
            )
            response.raise_for_status()
            batch: list[dict] = response.json()

            if not batch:
                break

            activities.extend(a for a in batch if a.get("type") == "Run")
            page += 1

        return activities

    def normalize(self, raw: list[dict]) -> list[dict]:
        """Transform raw Strava activity dicts into the activities table schema."""
        records = []
        for a in raw:
            distance_m: float = a.get("distance") or 0
            duration_s: int = a.get("moving_time") or 0
            avg_pace = (duration_s / (distance_m / 1000)) if distance_m > 0 else None

            start_local: str = a.get("start_date_local", "")
            activity_date = (
                datetime.fromisoformat(start_local.replace("Z", "")).date()
                if start_local
                else None
            )

            records.append(
                {
                    "id": uuid.uuid4(),
                    "strava_activity_id": a["id"],
                    "date": activity_date,
                    "start_time": a.get("start_date"),
                    "name": a.get("name"),
                    "distance_meters": distance_m,
                    "duration_seconds": duration_s,
                    "elapsed_time_seconds": a.get("elapsed_time"),
                    "avg_pace_sec_per_km": avg_pace,
                    "avg_heart_rate": a.get("average_heartrate"),
                    "max_heart_rate": a.get("max_heartrate"),
                    "avg_cadence": a.get("average_cadence"),
                    "elevation_gain_meters": a.get("total_elevation_gain"),
                    "suffer_score": a.get("suffer_score"),
                    "pr_count": a.get("pr_count", 0),
                    "perceived_effort": a.get("perceived_exertion"),
                }
            )
        return records

    def upsert(self, records: list[dict]) -> int:
        """Insert activities, skipping any that already exist (dedup on strava_activity_id)."""
        if not records:
            return 0

        with get_connection() as conn:
            stmt = (
                insert(Activity)
                .values(records)
                .on_conflict_do_nothing(index_elements=["strava_activity_id"])
            )
            result = conn.execute(stmt)
            conn.commit()
            return result.rowcount
