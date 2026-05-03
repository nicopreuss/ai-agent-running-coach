from datetime import datetime, timezone
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
