import datetime
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.dashboard import (
    DashboardSummary,
    LastRunSnapshot,
    NextSessionSnapshot,
    WhoopSnapshot,
    get_dashboard_summary,
    get_last_run_snapshot,
    get_next_session_snapshot,
    get_whoop_snapshot,
)
from api.main import app


def _mock_row(data: dict):
    row = MagicMock()
    row.__getitem__ = lambda self, k: data[k]
    return row


def test_get_whoop_snapshot_returns_data():
    data = {
        "recovery_score": 82.0,
        "sleep_performance_pct": 79.0,
        "daily_strain": 12.4,
        "date": datetime.date(2026, 5, 4),
    }
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = _mock_row(data)

    result = get_whoop_snapshot(conn)

    assert isinstance(result, WhoopSnapshot)
    assert result.recovery_score == 82.0
    assert result.sleep_performance_pct == 79.0
    assert result.daily_strain == 12.4
    assert result.date == datetime.date(2026, 5, 4)


def test_get_whoop_snapshot_returns_none_when_no_data():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = None

    assert get_whoop_snapshot(conn) is None


def test_get_last_run_snapshot_converts_meters_to_km():
    data = {
        "distance_meters": 8200.0,
        "duration_seconds": 2712,
        "avg_pace_sec_per_km": 330.0,
        "avg_heart_rate": 148.0,
        "date": datetime.date(2026, 5, 4),
    }
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = _mock_row(data)

    result = get_last_run_snapshot(conn)

    assert isinstance(result, LastRunSnapshot)
    assert result.distance_km == 8.2
    assert result.duration_seconds == 2712
    assert result.avg_pace_sec_per_km == 330.0
    assert result.avg_heart_rate == 148.0


def test_get_last_run_snapshot_returns_none_when_no_data():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = None

    assert get_last_run_snapshot(conn) is None


def test_get_next_session_snapshot_returns_next_upcoming():
    data = {
        "title": "Fast 8-4-2s · 8.1km",
        "date": datetime.date(2026, 5, 6),
    }
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = _mock_row(data)

    result = get_next_session_snapshot(conn)

    assert isinstance(result, NextSessionSnapshot)
    assert result.title == "Fast 8-4-2s · 8.1km"
    assert result.date == datetime.date(2026, 5, 6)


def test_get_next_session_snapshot_returns_none_when_no_data():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = None

    assert get_next_session_snapshot(conn) is None


def test_get_dashboard_summary_assembles_all_sections():
    whoop = WhoopSnapshot(
        recovery_score=82.0,
        sleep_performance_pct=79.0,
        daily_strain=12.4,
        date=datetime.date(2026, 5, 4),
    )
    run = LastRunSnapshot(
        distance_km=8.2,
        duration_seconds=2712,
        avg_pace_sec_per_km=330.0,
        avg_heart_rate=148.0,
        date=datetime.date(2026, 5, 4),
    )
    session = NextSessionSnapshot(title="Fast 8-4-2s · 8.1km", date=datetime.date(2026, 5, 6))

    mock_conn = MagicMock()
    with patch("api.dashboard.get_connection") as mock_get_conn:
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        with patch("api.dashboard.get_whoop_snapshot", return_value=whoop):
            with patch("api.dashboard.get_last_run_snapshot", return_value=run):
                with patch("api.dashboard.get_next_session_snapshot", return_value=session):
                    result = get_dashboard_summary()

    assert isinstance(result, DashboardSummary)
    assert result.whoop == whoop
    assert result.last_run == run
    assert result.next_session == session


def test_get_dashboard_summary_handles_empty_db():
    mock_conn = MagicMock()
    with patch("api.dashboard.get_connection") as mock_get_conn:
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        with patch("api.dashboard.get_whoop_snapshot", return_value=None):
            with patch("api.dashboard.get_last_run_snapshot", return_value=None):
                with patch("api.dashboard.get_next_session_snapshot", return_value=None):
                    result = get_dashboard_summary()

    assert result.whoop is None
    assert result.last_run is None
    assert result.next_session is None


def test_dashboard_summary_endpoint_returns_ok():
    whoop = WhoopSnapshot(
        recovery_score=82.0,
        sleep_performance_pct=79.0,
        daily_strain=12.4,
        date=datetime.date(2026, 5, 4),
    )
    run = LastRunSnapshot(
        distance_km=8.2,
        duration_seconds=2712,
        avg_pace_sec_per_km=330.0,
        avg_heart_rate=148.0,
        date=datetime.date(2026, 5, 4),
    )
    session = NextSessionSnapshot(title="Fast 8-4-2s · 8.1km", date=datetime.date(2026, 5, 6))
    summary = DashboardSummary(whoop=whoop, last_run=run, next_session=session)

    with patch("api.main.get_dashboard_summary", return_value=summary):
        with TestClient(app) as client:
            response = client.get("/dashboard/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["whoop"]["recovery_score"] == 82.0
    assert data["last_run"]["distance_km"] == 8.2
    assert data["next_session"]["title"] == "Fast 8-4-2s · 8.1km"


def test_dashboard_summary_endpoint_returns_nulls_when_empty():
    summary = DashboardSummary(whoop=None, last_run=None, next_session=None)

    with patch("api.main.get_dashboard_summary", return_value=summary):
        with TestClient(app) as client:
            response = client.get("/dashboard/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["whoop"] is None
    assert data["last_run"] is None
    assert data["next_session"] is None
