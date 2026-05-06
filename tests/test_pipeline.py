from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from db.models import IngestionStatus
from ingestion.pipeline import _read_watermark, run


def _mock_connection(scalar_result=None):
    """Return a mock context-manager connection that returns scalar_result on execute."""
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.scalar_one_or_none.return_value = scalar_result
    return conn


def test_read_watermark_returns_none_when_no_log():
    with patch("ingestion.pipeline.get_connection", return_value=_mock_connection(None)):
        result = _read_watermark("strava")
    assert result is None


def test_read_watermark_returns_timestamp_from_log():
    ts = datetime(2026, 5, 1, 8, 0, 0, tzinfo=timezone.utc)
    with patch("ingestion.pipeline.get_connection", return_value=_mock_connection(ts)):
        result = _read_watermark("whoop")
    assert result == ts


def test_run_strava_returns_correct_stats():
    mock_source = MagicMock()
    mock_source.fetch.return_value = [{"id": 1}, {"id": 2}]
    mock_source.normalize.return_value = [{"strava_activity_id": 1}, {"strava_activity_id": 2}]
    mock_source.upsert.return_value = 1  # 1 inserted, 1 skipped (already exists)

    with patch("ingestion.pipeline._read_watermark", return_value=None), \
         patch("ingestion.pipeline.StravaSource", return_value=mock_source), \
         patch("ingestion.pipeline._write_log") as mock_log:
        result = run("strava")

    assert result == {"records_fetched": 2, "records_inserted": 1, "records_skipped": 1}
    mock_log.assert_called_once_with("strava", IngestionStatus.success, 2, 1, 1, error=None)


def test_run_whoop_returns_correct_stats():
    mock_source = MagicMock()
    mock_source.fetch.return_value = [{"cycle": {}}]
    mock_source.normalize.return_value = [{"date": "2026-05-01"}]
    mock_source.upsert.return_value = 1

    with patch("ingestion.pipeline._read_watermark", return_value=None), \
         patch("ingestion.pipeline.WhoopSource", return_value=mock_source), \
         patch("ingestion.pipeline._write_log") as mock_log:
        result = run("whoop")

    assert result == {"records_fetched": 1, "records_inserted": 1, "records_skipped": 0}
    mock_log.assert_called_once_with("whoop", IngestionStatus.success, 1, 1, 0, error=None)


def test_run_writes_failed_log_on_exception():
    mock_source = MagicMock()
    mock_source.fetch.side_effect = RuntimeError("API down")

    with patch("ingestion.pipeline._read_watermark", return_value=None), \
         patch("ingestion.pipeline.StravaSource", return_value=mock_source), \
         patch("ingestion.pipeline._write_log") as mock_log:
        with pytest.raises(RuntimeError):
            run("strava")

    mock_log.assert_called_once_with("strava", IngestionStatus.failed, 0, 0, 0, error="API down")


def test_run_raises_for_unknown_source():
    with patch("ingestion.pipeline._read_watermark", return_value=None):
        with pytest.raises(ValueError, match="unknown_source"):
            run("unknown_source")


def test_run_google_calendar_returns_correct_stats():
    mock_source = MagicMock()
    mock_source.fetch.return_value = [{"id": "evt1"}, {"id": "evt2"}]
    mock_source.normalize.return_value = [
        {"google_event_id": "evt1"},
        {"google_event_id": "evt2"},
    ]
    mock_source.upsert.return_value = 2

    with patch("ingestion.pipeline._read_watermark", return_value=None), \
         patch("ingestion.pipeline.GoogleCalendarSource", return_value=mock_source), \
         patch("ingestion.pipeline._write_log") as mock_log:
        result = run("google_calendar")

    assert result == {"records_fetched": 2, "records_inserted": 2, "records_skipped": 0}
    mock_log.assert_called_once_with(
        "google_calendar", IngestionStatus.success, 2, 2, 0, error=None
    )


def test_run_whoop_clamps_start_date_to_today_when_watermark_is_later_today():
    """Watermark later in the day must be clamped to 00:00:00 today."""
    today = date.today()
    # Simulate a watermark set at 14:00 today (after this morning's cycle started)
    watermark = datetime.combine(today, time(14, 0, 0)).replace(tzinfo=timezone.utc)
    expected_start = datetime.combine(today, time.min).replace(tzinfo=timezone.utc)
    expected_str = expected_start.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    mock_source = MagicMock()
    mock_source.fetch.return_value = []
    mock_source.normalize.return_value = []
    mock_source.upsert.return_value = 0
    captured = {}

    def capture(start_date=None):
        captured["start_date"] = start_date
        return mock_source

    with patch("ingestion.pipeline._read_watermark", return_value=watermark), \
         patch("ingestion.pipeline.WhoopSource", side_effect=capture), \
         patch("ingestion.pipeline._write_log"):
        run("whoop")

    assert captured["start_date"] == expected_str


def test_run_whoop_uses_watermark_unchanged_when_before_today():
    """Watermark from a previous day must be used as-is (no clamping)."""
    yesterday = date.today() - timedelta(days=1)
    watermark = datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=timezone.utc)
    expected_str = watermark.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    mock_source = MagicMock()
    mock_source.fetch.return_value = []
    mock_source.normalize.return_value = []
    mock_source.upsert.return_value = 0
    captured = {}

    def capture(start_date=None):
        captured["start_date"] = start_date
        return mock_source

    with patch("ingestion.pipeline._read_watermark", return_value=watermark), \
         patch("ingestion.pipeline.WhoopSource", side_effect=capture), \
         patch("ingestion.pipeline._write_log"):
        run("whoop")

    assert captured["start_date"] == expected_str
