"""SQLAlchemy ORM model definitions.

Define one class per database table using the DeclarativeBase pattern.
All models should live here (or be imported here) so Alembic can auto-generate
migrations from a single metadata object.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Float, Integer, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Shared declarative base — all models inherit from this.

    DeclarativeBase automatically creates and manages its own MetaData registry.
    Do not override Base.metadata — doing so severs the link between the base
    and its model registry, causing create_all() and Alembic autogenerate to
    silently miss all models.
    """


class StravaActivity(Base):
    __tablename__ = "strava_activities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strava_activity_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elapsed_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_pace_sec_per_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_heart_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_heart_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_cadence: Mapped[float | None] = mapped_column(Float, nullable=True)
    elevation_gain_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    suffer_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    perceived_effort: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WhoopRecoveryDaily(Base):
    __tablename__ = "whoop_recovery_daily"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    whoop_cycle_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    recovery_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hrv_rmssd_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    resting_heart_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_performance_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_efficiency_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    swo_deep_sleep_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rem_sleep_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    light_sleep_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sleep_consistency_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_strain: Mapped[float | None] = mapped_column(Float, nullable=True)
    skin_temp_celsius: Mapped[float | None] = mapped_column(Float, nullable=True)
    spo2_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IngestionSource(enum.Enum):
    whoop = "whoop"
    strava = "strava"
    google_calendar = "google_calendar"


class IngestionStatus(enum.Enum):
    success = "success"
    partial = "partial"
    failed = "failed"


class IngestionLog(Base):
    __tablename__ = "ingestion_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[IngestionSource] = mapped_column(
        SAEnum(IngestionSource, native_enum=False, length=50), nullable=False
    )
    status: Mapped[IngestionStatus] = mapped_column(
        SAEnum(IngestionStatus, native_enum=False, length=20), nullable=False
    )
    records_fetched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_inserted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_skipped: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
