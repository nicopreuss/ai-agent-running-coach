"""Dashboard summary: query functions and response models for GET /dashboard/summary."""

import datetime

from pydantic import BaseModel
from sqlalchemy import text

from db.client import get_connection


class WhoopSnapshot(BaseModel):
    recovery_score: float
    sleep_performance_pct: float
    daily_strain: float
    date: datetime.date


class LastRunSnapshot(BaseModel):
    distance_km: float
    duration_seconds: int
    avg_pace_sec_per_km: float
    avg_heart_rate: float
    date: datetime.date


class NextSessionSnapshot(BaseModel):
    title: str
    date: datetime.date


class DashboardSummary(BaseModel):
    whoop: WhoopSnapshot | None
    last_run: LastRunSnapshot | None
    next_session: NextSessionSnapshot | None


def get_whoop_snapshot(conn) -> WhoopSnapshot | None:
    row = (
        conn.execute(
            text(
                """
                SELECT recovery_score, sleep_performance_pct, daily_strain, date
                FROM whoop_recovery_daily
                ORDER BY date DESC
                LIMIT 1
                """
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return WhoopSnapshot(
        recovery_score=row["recovery_score"],
        sleep_performance_pct=row["sleep_performance_pct"],
        daily_strain=row["daily_strain"],
        date=row["date"],
    )


def get_last_run_snapshot(conn) -> LastRunSnapshot | None:
    row = (
        conn.execute(
            text(
                """
                SELECT distance_meters, duration_seconds, avg_pace_sec_per_km,
                       avg_heart_rate, date
                FROM strava_activities
                ORDER BY date DESC
                LIMIT 1
                """
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return LastRunSnapshot(
        distance_km=round(row["distance_meters"] / 1000, 1),
        duration_seconds=row["duration_seconds"],
        avg_pace_sec_per_km=row["avg_pace_sec_per_km"],
        avg_heart_rate=row["avg_heart_rate"],
        date=row["date"],
    )


def get_next_session_snapshot(conn) -> NextSessionSnapshot | None:
    row = (
        conn.execute(
            text(
                """
                SELECT title, date
                FROM google_calendar_runna_sessions
                WHERE date >= CURRENT_DATE
                ORDER BY date ASC
                LIMIT 1
                """
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return NextSessionSnapshot(title=row["title"], date=row["date"])


def get_dashboard_summary() -> DashboardSummary:
    with get_connection() as conn:
        return DashboardSummary(
            whoop=get_whoop_snapshot(conn),
            last_run=get_last_run_snapshot(conn),
            next_session=get_next_session_snapshot(conn),
        )
