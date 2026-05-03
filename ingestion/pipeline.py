"""Ingestion pipeline: orchestrates fetch → normalize → upsert for each data source."""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert

from db.client import get_connection
from db.models import IngestionLog, IngestionSource, IngestionStatus
from ingestion.sources.base import DataSource
from ingestion.sources.strava import StravaSource
from ingestion.sources.whoop import WhoopSource

logger = logging.getLogger(__name__)


def _read_watermark(source_name: str) -> datetime | None:
    """Return last_fetched_at from the most recent successful ingestion for this source."""
    with get_connection() as conn:
        stmt = (
            select(IngestionLog.last_fetched_at)
            .where(IngestionLog.source == IngestionSource(source_name))
            .where(IngestionLog.status == IngestionStatus.success)
            .order_by(desc(IngestionLog.created_at))
            .limit(1)
        )
        return conn.execute(stmt).scalar_one_or_none()


def _write_log(
    source_name: str,
    status: IngestionStatus,
    fetched: int,
    inserted: int,
    skipped: int,
    error: str | None = None,
) -> None:
    """Write an ingestion_log row. On success, sets last_fetched_at to now."""
    now = datetime.now(tz=timezone.utc)
    record = {
        "id": uuid.uuid4(),
        "source": IngestionSource(source_name),
        "status": status,
        "records_fetched": fetched,
        "records_inserted": inserted,
        "records_skipped": skipped,
        "last_fetched_at": now if status == IngestionStatus.success else None,
        "error_message": error,
    }
    with get_connection() as conn:
        conn.execute(insert(IngestionLog).values([record]))
        conn.commit()


def run(source_name: str) -> dict:
    """Run incremental ingestion for one source using the watermark from ingestion_log.

    Args:
        source_name: "strava" or "whoop"

    Returns:
        dict with records_fetched, records_inserted, records_skipped
    """
    logger.info("Starting ingestion for source: %s", source_name)

    watermark = _read_watermark(source_name)
    logger.info("Watermark for %s: %s", source_name, watermark)

    if source_name == "strava":
        after_ts = int(watermark.timestamp()) if watermark else None
        source: DataSource = StravaSource(after_timestamp=after_ts)
    elif source_name == "whoop":
        start_date = watermark.strftime("%Y-%m-%dT%H:%M:%S.000Z") if watermark else None
        source = WhoopSource(start_date=start_date)
    else:
        raise ValueError(f"Unknown source: {source_name!r}")

    try:
        raw = source.fetch()
        logger.info("Fetched %d raw records from %s", len(raw), source_name)

        normalised = source.normalize(raw)
        inserted = source.upsert(normalised)
        skipped = len(normalised) - inserted

        logger.info("Upserted %d records (%d skipped) for %s", inserted, skipped, source_name)
        _write_log(source_name, IngestionStatus.success, len(raw), inserted, skipped, error=None)

        return {
            "records_fetched": len(raw),
            "records_inserted": inserted,
            "records_skipped": skipped,
        }

    except Exception as exc:
        logger.exception("Ingestion failed for %s: %s", source_name, exc)
        _write_log(source_name, IngestionStatus.failed, 0, 0, 0, error=str(exc))
        raise


def run_pipeline(sources: list[DataSource]) -> None:
    """Execute the full ingestion pipeline for every provided source.

    Args:
        sources: List of DataSource instances to run in sequence.
    """
    for source in sources:
        name = type(source).__name__
        logger.info("Starting ingestion for source: %s", name)

        raw = source.fetch()
        logger.info("Fetched %d raw records from %s", len(raw), name)

        normalised = source.normalize(raw)
        logger.info("Normalised %d records from %s", len(normalised), name)

        written = source.upsert(normalised)
        logger.info("Upserted %d records from %s", written, name)

    logger.info("Pipeline complete for %d source(s).", len(sources))
