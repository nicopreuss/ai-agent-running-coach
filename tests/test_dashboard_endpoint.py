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
        "efficiency_factor": 1.35,
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
    assert result.efficiency_factor == 1.35


def test_get_last_run_snapshot_returns_none_when_no_data():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = None

    assert get_last_run_snapshot(conn) is None


def test_get_next_session_snapshot_returns_next_upcoming():
    data = {
        "title": "Fast 8-4-2s · 8.1km",
        "date": datetime.date(2026, 5, 6),
        "description": "Intervals session with warmup and cooldown",
    }
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = _mock_row(data)

    result = get_next_session_snapshot(conn)

    assert isinstance(result, NextSessionSnapshot)
    assert result.title == "Fast 8-4-2s · 8.1km"
    assert result.date == datetime.date(2026, 5, 6)
    assert result.description == "Intervals session with warmup and cooldown"


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
    session = NextSessionSnapshot(
        title="Fast 8-4-2s · 8.1km", date=datetime.date(2026, 5, 6), description=None
    )

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
    session = NextSessionSnapshot(
        title="Fast 8-4-2s · 8.1km", date=datetime.date(2026, 5, 6), description=None
    )
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


def test_get_last_run_snapshot_includes_ef_when_present():
    data = {
        "distance_meters": 5000.0,
        "duration_seconds": 1500,
        "avg_pace_sec_per_km": 300.0,
        "avg_heart_rate": 150.0,
        "efficiency_factor": 1.33,
        "date": datetime.date(2026, 5, 4),
    }
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = _mock_row(data)

    result = get_last_run_snapshot(conn)

    assert result.efficiency_factor == 1.33


def test_get_last_run_snapshot_ef_is_none_when_null():
    data = {
        "distance_meters": 5000.0,
        "duration_seconds": 1500,
        "avg_pace_sec_per_km": 300.0,
        "avg_heart_rate": 150.0,
        "efficiency_factor": None,
        "date": datetime.date(2026, 5, 4),
    }
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = _mock_row(data)

    result = get_last_run_snapshot(conn)

    assert result.efficiency_factor is None


def test_recovery_colour_green():
    from ui.app import _recovery_colour
    assert _recovery_colour(70.0) == "#4ade80"
    assert _recovery_colour(85.0) == "#4ade80"
    assert _recovery_colour(100.0) == "#4ade80"


def test_recovery_colour_yellow():
    from ui.app import _recovery_colour
    assert _recovery_colour(40.0) == "#facc15"
    assert _recovery_colour(55.0) == "#facc15"
    assert _recovery_colour(69.9) == "#facc15"


def test_recovery_colour_red():
    from ui.app import _recovery_colour
    assert _recovery_colour(0.0) == "#f87171"
    assert _recovery_colour(39.9) == "#f87171"


def test_get_weekly_ef_trend_returns_data():
    from api.dashboard import WeeklyEFPoint, get_weekly_ef_trend

    row1 = _mock_row({"week_start": datetime.date(2026, 2, 3), "weekly_ef": 1.42})
    row2 = _mock_row({"week_start": datetime.date(2026, 2, 10), "weekly_ef": 1.45})
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = [row1, row2]

    result = get_weekly_ef_trend(conn)

    assert len(result) == 2
    assert isinstance(result[0], WeeklyEFPoint)
    assert result[0].week_start == datetime.date(2026, 2, 3)
    assert result[0].weekly_ef == 1.42
    assert result[1].week_start == datetime.date(2026, 2, 10)
    assert result[1].weekly_ef == 1.45


def test_get_weekly_ef_trend_returns_empty_when_no_data():
    from api.dashboard import get_weekly_ef_trend

    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = []

    result = get_weekly_ef_trend(conn)

    assert result == []
