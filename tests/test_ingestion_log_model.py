from db.models import IngestionLog, IngestionSource, IngestionStatus


def test_ingestion_log_table_name():
    assert IngestionLog.__tablename__ == "ingestion_log"


def test_ingestion_log_has_required_columns():
    cols = {c.key for c in IngestionLog.__table__.columns}
    assert cols >= {"id", "source", "status", "records_fetched", "records_inserted",
                    "records_skipped", "last_fetched_at", "error_message", "created_at"}


def test_ingestion_source_enum_values():
    assert IngestionSource.whoop.value == "whoop"
    assert IngestionSource.strava.value == "strava"
    assert IngestionSource.google_calendar.value == "google_calendar"


def test_ingestion_status_enum_values():
    assert IngestionStatus.success.value == "success"
    assert IngestionStatus.partial.value == "partial"
    assert IngestionStatus.failed.value == "failed"
