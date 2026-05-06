"""Unit tests for WhoopSource._paginate() and normalize()."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def whoop_env(monkeypatch):
    monkeypatch.setenv("WHOOP_CLIENT_ID", "test-id")
    monkeypatch.setenv("WHOOP_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("WHOOP_REFRESH_TOKEN", "test-refresh")
    monkeypatch.setenv("WHOOP_ACCESS_TOKEN", "test-access")


def test_paginate_single_page():
    from ingestion.sources.whoop import WhoopSource

    source = WhoopSource()

    page = {"records": [{"id": 1}, {"id": 2}], "next_token": None}
    source._get = MagicMock(return_value=page)

    result = source._paginate("/cycle")

    assert result == [{"id": 1}, {"id": 2}]
    source._get.assert_called_once_with("/cycle", {"limit": 25})


def test_paginate_multiple_pages():
    from ingestion.sources.whoop import WhoopSource

    source = WhoopSource()

    page1 = {"records": [{"id": 1}], "next_token": "tok123"}
    page2 = {"records": [{"id": 2}], "next_token": None}
    source._get = MagicMock(side_effect=[page1, page2])

    result = source._paginate("/cycle")

    assert result == [{"id": 1}, {"id": 2}]
    assert source._get.call_count == 2
    source._get.assert_called_with("/cycle", {"limit": 25, "nextToken": "tok123"})


def test_fetch_joins_cycle_recovery_sleep():
    from ingestion.sources.whoop import WhoopSource

    source = WhoopSource()

    cycles = [{"id": 42, "start": "2024-01-15T06:00:00Z", "score": {"strain": 8.5}}]
    recoveries = [{"cycle_id": 42, "score": {"recovery_score": 85.0, "hrv_rmssd_milli": 72.3}}]
    sleeps = [{"cycle_id": 42, "nap": False, "score": {"sleep_performance_percentage": 90.0}}]

    def fake_paginate(path, params=None):
        if path == "/cycle":
            return cycles
        if path == "/recovery":
            return recoveries
        if path == "/activity/sleep":
            return sleeps
        return []

    source._paginate = MagicMock(side_effect=fake_paginate)

    result = source.fetch()

    assert len(result) == 1
    assert result[0]["cycle"]["id"] == 42
    assert result[0]["recovery"]["score"]["recovery_score"] == 85.0
    assert result[0]["sleep"]["score"]["sleep_performance_percentage"] == 90.0


def test_fetch_filters_naps():
    from ingestion.sources.whoop import WhoopSource

    source = WhoopSource()

    cycles = [{"id": 42, "start": "2024-01-15T06:00:00Z", "score": {}}]
    recoveries = [{"cycle_id": 42, "score": {}}]
    sleeps = [
        {"cycle_id": 42, "nap": False, "score": {}},
        {"cycle_id": 42, "nap": True, "score": {}},
    ]

    def fake_paginate(path, params=None):
        if path == "/cycle":
            return cycles
        if path == "/recovery":
            return recoveries
        if path == "/activity/sleep":
            return sleeps
        return []

    source._paginate = MagicMock(side_effect=fake_paginate)
    result = source.fetch()

    assert result[0]["sleep"].get("nap") is False


def test_fetch_skips_cycle_with_no_recovery():
    from ingestion.sources.whoop import WhoopSource

    source = WhoopSource()

    cycles = [
        {"id": 42, "start": "2024-01-15T06:00:00Z", "score": {}},
        {"id": 99, "start": "2024-01-16T06:00:00Z", "score": {}},
    ]
    recoveries = [{"cycle_id": 42, "score": {}}]

    def fake_paginate(path, params=None):
        if path == "/cycle":
            return cycles
        if path == "/recovery":
            return recoveries
        if path == "/activity/sleep":
            return []
        return []

    source._paginate = MagicMock(side_effect=fake_paginate)
    result = source.fetch()

    assert len(result) == 1
    assert result[0]["cycle"]["id"] == 42


def test_normalize_maps_all_fields():
    from datetime import date

    from ingestion.sources.whoop import WhoopSource

    source = WhoopSource()

    raw = [{
        "cycle": {
            "id": 42,
            "start": "2024-01-15T06:00:00Z",
            "score": {"strain": 8.5},
        },
        "recovery": {
            "cycle_id": 42,
            "score": {
                "recovery_score": 85.0,
                "hrv_rmssd_milli": 72.3,
                "resting_heart_rate": 48.0,
                "skin_temp_celsius": 36.1,
                "spo2_percentage": 98.0,
            },
        },
        "sleep": {
            "cycle_id": 42,
            "score": {
                "sleep_performance_percentage": 90.0,
                "sleep_efficiency_percentage": 88.0,
                "sleep_consistency_percentage": 75.0,
                "stage_summary": {
                    "total_in_bed_time_milli": 28800000,
                    "slow_wave_sleep_duration_milli": 5400000,
                    "rem_sleep_duration_milli": 7200000,
                    "light_sleep_duration_milli": 10800000,
                },
            },
        },
    }]

    records = source.normalize(raw)

    assert len(records) == 1
    r = records[0]
    assert r["date"] == date(2024, 1, 15)
    assert r["whoop_cycle_id"] == 42
    assert r["recovery_score"] == 85.0
    assert r["hrv_rmssd_ms"] == 72.3
    assert r["resting_heart_rate"] == 48.0
    assert r["daily_strain"] == 8.5
    assert r["sleep_performance_pct"] == 90.0
    assert r["sleep_efficiency_pct"] == 88.0
    assert r["sleep_consistency_pct"] == 75.0
    assert r["sleep_duration_ms"] == 28800000
    assert r["swo_deep_sleep_ms"] == 5400000
    assert r["rem_sleep_ms"] == 7200000
    assert r["light_sleep_ms"] == 10800000
    assert r["skin_temp_celsius"] == 36.1
    assert r["spo2_percentage"] == 98.0


def test_normalize_handles_missing_sleep():
    from ingestion.sources.whoop import WhoopSource

    source = WhoopSource()

    raw = [{
        "cycle": {"id": 99, "start": "2024-01-16T06:00:00Z", "score": {"strain": 5.0}},
        "recovery": {
            "cycle_id": 99,
            "score": {"recovery_score": 70.0, "hrv_rmssd_milli": 60.0, "resting_heart_rate": 52.0},
        },
        "sleep": {},
    }]

    records = source.normalize(raw)

    assert len(records) == 1
    assert records[0]["sleep_performance_pct"] is None
    assert records[0]["sleep_duration_ms"] is None
    assert records[0]["recovery_score"] == 70.0


def test_upsert_calls_on_conflict_do_update_for_daily_strain():
    """upsert() must use on_conflict_do_update targeting daily_strain."""
    from datetime import date
    from unittest.mock import MagicMock, patch

    from ingestion.sources.whoop import WhoopSource

    source = WhoopSource()
    records = [{"date": date.today(), "whoop_cycle_id": 1, "daily_strain": 12.3}]

    mock_ins = MagicMock()
    mock_ins.values.return_value = mock_ins
    mock_ins.on_conflict_do_update.return_value = mock_ins
    mock_ins.excluded.daily_strain = "excluded_daily_strain_sentinel"

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.rowcount = 1

    with patch("ingestion.sources.whoop.insert", return_value=mock_ins), \
         patch("ingestion.sources.whoop.get_connection", return_value=mock_conn):
        result = source.upsert(records)

    mock_ins.on_conflict_do_update.assert_called_once()
    kwargs = mock_ins.on_conflict_do_update.call_args.kwargs
    assert kwargs["index_elements"] == ["whoop_cycle_id"]
    assert "daily_strain" in kwargs["set_"]
    assert kwargs.get("where") is not None
    mock_conn.commit.assert_called_once()
    assert result == 1


def test_upsert_returns_zero_and_skips_db_for_empty_records():
    """upsert([]) must return 0 without touching the database."""
    from unittest.mock import MagicMock, patch

    from ingestion.sources.whoop import WhoopSource

    source = WhoopSource()

    with patch("ingestion.sources.whoop.get_connection") as mock_get_conn:
        result = source.upsert([])

    assert result == 0
    mock_get_conn.assert_not_called()
