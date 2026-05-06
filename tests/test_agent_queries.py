"""Unit tests for agent.queries — mock DB connections, no real DB required."""

import datetime
from unittest.mock import MagicMock

from agent.queries import get_training_and_recovery, get_upcoming_sessions


def _mock_row(data: dict):
    row = MagicMock()
    row.__getitem__ = lambda self, k: data[k]
    return row


def test_get_training_and_recovery_with_run_and_rest_day():
    row_run = _mock_row({
        "date": datetime.date(2026, 5, 5),
        "recovery_score": 78.0,
        "hrv_rmssd_ms": 62.0,
        "resting_heart_rate": 48.0,
        "sleep_performance_pct": 85.0,
        "sleep_duration_ms": 24300000,
        "daily_strain": 12.3,
        "run_name": "Morning Run",
        "distance_meters": 10200.0,
        "duration_seconds": 3510,
        "avg_pace_sec_per_km": 344.0,
        "avg_heart_rate": 152.0,
        "efficiency_factor": 1.42,
    })
    row_rest = _mock_row({
        "date": datetime.date(2026, 5, 4),
        "recovery_score": 65.0,
        "hrv_rmssd_ms": 55.0,
        "resting_heart_rate": 51.0,
        "sleep_performance_pct": 72.0,
        "sleep_duration_ms": 21000000,
        "daily_strain": 8.1,
        "run_name": None,
        "distance_meters": None,
        "duration_seconds": None,
        "avg_pace_sec_per_km": None,
        "avg_heart_rate": None,
        "efficiency_factor": None,
    })
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = [row_run, row_rest]

    result = get_training_and_recovery(conn, lookback_days=7)

    assert "2026-05-05 (Tue)" in result
    assert "2026-05-04 (Mon)" in result
    assert "Recovery: 78%" in result
    assert "Morning Run" in result
    assert "10.2km" in result
    assert "No run recorded." in result


def test_get_training_and_recovery_no_data():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = []

    result = get_training_and_recovery(conn, lookback_days=7)

    assert "No training or recovery data" in result


def test_get_training_and_recovery_rejects_over_90_days():
    conn = MagicMock()

    result = get_training_and_recovery(conn, lookback_days=91)

    assert "Error" in result
    assert "90 days" in result
    conn.execute.assert_not_called()


def test_get_upcoming_sessions_returns_sessions():
    row1 = _mock_row({
        "date": datetime.date(2026, 5, 7),
        "title": "Easy Run",
        "description": "45min easy effort, HR cap 145bpm",
    })
    row2 = _mock_row({
        "date": datetime.date(2026, 5, 9),
        "title": "Tempo Intervals",
        "description": None,
    })
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = [row1, row2]

    result = get_upcoming_sessions(conn, days_ahead=7)

    assert "2026-05-07 (Thu)" in result
    assert "Easy Run" in result
    assert "45min easy effort" in result
    assert "2026-05-09 (Sat)" in result
    assert "Tempo Intervals" in result


def test_get_upcoming_sessions_no_sessions():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = []

    result = get_upcoming_sessions(conn, days_ahead=7)

    assert "No upcoming sessions" in result


def test_get_upcoming_sessions_rejects_over_90_days():
    conn = MagicMock()

    result = get_upcoming_sessions(conn, days_ahead=91)

    assert "Error" in result
    assert "90 days" in result
    conn.execute.assert_not_called()
