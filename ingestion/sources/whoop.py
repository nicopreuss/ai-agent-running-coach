"""Whoop data source: fetches, normalises, and upserts daily recovery data."""

import os
import time
from datetime import datetime

import requests
from dotenv import find_dotenv, load_dotenv, set_key
from sqlalchemy.dialects.postgresql import insert

from db.client import get_connection
from db.models import WhoopRecoveryDaily
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
        env_path = find_dotenv()
        set_key(env_path, "WHOOP_ACCESS_TOKEN", self._access_token)
        set_key(env_path, "WHOOP_REFRESH_TOKEN", self._refresh_token)

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
            time.sleep(0.5)
            next_token = data.get("next_token")
            if not next_token:
                break
        return results

    # ── DataSource interface (stubs — filled in next step) ────────────────────

    def fetch(self) -> list[dict]:
        """Fetch all daily records from Whoop, joining cycle + recovery + sleep data."""
        params = {"start": self._start_date} if self._start_date else {}

        cycles     = {c["id"]: c for c in self._paginate("/cycle", params)}
        recoveries = {r["cycle_id"]: r for r in self._paginate("/recovery", params)}
        sleeps     = {
            s["cycle_id"]: s
            for s in self._paginate("/activity/sleep", params)
            if not s.get("nap")
        }

        return [
            {"cycle": cycles[cid], "recovery": recoveries[cid], "sleep": sleeps.get(cid, {})}
            for cid in recoveries
            if cid in cycles
        ]

    def normalize(self, raw: list[dict]) -> list[dict]:
        """Map merged Whoop dicts to the whoop_recovery_daily table schema."""
        records = []
        for r in raw:
            cycle          = r["cycle"]
            recovery       = r["recovery"]
            sleep          = r.get("sleep", {})
            cycle_score    = cycle.get("score") or {}
            recovery_score = recovery.get("score") or {}
            sleep_score    = sleep.get("score") or {}
            stages         = sleep_score.get("stage_summary") or {}

            start = cycle.get("start", "")
            activity_date = (
                datetime.fromisoformat(start.replace("Z", "")).date()
                if start else None
            )

            records.append({
                "date": activity_date,
                "whoop_cycle_id": cycle["id"],
                "recovery_score": recovery_score.get("recovery_score"),
                "hrv_rmssd_ms": recovery_score.get("hrv_rmssd_milli"),
                "resting_heart_rate": recovery_score.get("resting_heart_rate"),
                "sleep_performance_pct": sleep_score.get("sleep_performance_percentage"),
                "sleep_efficiency_pct": sleep_score.get("sleep_efficiency_percentage"),
                "sleep_consistency_pct": sleep_score.get("sleep_consistency_percentage"),
                "sleep_duration_ms": stages.get("total_in_bed_time_milli"),
                "swo_deep_sleep_ms": stages.get("slow_wave_sleep_duration_milli"),
                "rem_sleep_ms": stages.get("rem_sleep_duration_milli"),
                "light_sleep_ms": stages.get("light_sleep_duration_milli"),
                "daily_strain": cycle_score.get("strain"),
                "skin_temp_celsius": recovery_score.get("skin_temp_celsius"),
                "spo2_percentage": recovery_score.get("spo2_percentage"),
            })
        seen: dict = {}
        for r in records:
            d = r["date"]
            if d not in seen or (r["whoop_cycle_id"] or 0) > (seen[d]["whoop_cycle_id"] or 0):
                seen[d] = r
        return list(seen.values())

    def upsert(self, records: list[dict]) -> int:
        """Insert recovery records, skipping any that already exist (dedup on whoop_cycle_id)."""
        if not records:
            return 0

        with get_connection() as conn:
            stmt = (
                insert(WhoopRecoveryDaily)
                .values(records)
                .on_conflict_do_nothing(index_elements=["whoop_cycle_id"])
            )
            result = conn.execute(stmt)
            conn.commit()
            return result.rowcount
