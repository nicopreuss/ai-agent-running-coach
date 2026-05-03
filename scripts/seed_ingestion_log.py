"""One-time seed: write bootstrap ingestion_log entries so the first incremental
run fetches only recent data rather than re-fetching all history."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select

from db.client import get_connection, get_engine
from db.models import Base, IngestionLog, IngestionSource, IngestionStatus


def main() -> None:
    Base.metadata.create_all(get_engine())
    watermark = datetime.now(tz=timezone.utc) - timedelta(days=3)

    with get_connection() as conn:
        for source in IngestionSource:
            existing = conn.execute(
                select(IngestionLog.id).where(IngestionLog.source == source).limit(1)
            ).scalar_one_or_none()

            if existing:
                print(f"Skipping {source.value} — log entry already exists.")
                continue

            conn.execute(
                insert(IngestionLog).values([{
                    "id": uuid.uuid4(),
                    "source": source,
                    "status": IngestionStatus.success,
                    "records_fetched": 0,
                    "records_inserted": 0,
                    "records_skipped": 0,
                    "last_fetched_at": watermark,
                    "error_message": None,
                }])
            )
            print(f"Seeded {source.value} with watermark {watermark.isoformat()}")

        conn.commit()


if __name__ == "__main__":
    main()
