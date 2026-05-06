"""Unit tests for StravaSource.normalize() — efficiency factor computation."""

import pytest


@pytest.fixture(autouse=True)
def strava_env(monkeypatch):
    monkeypatch.setenv("STRAVA_CLIENT_ID", "test-id")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("STRAVA_REFRESH_TOKEN", "test-refresh")
    monkeypatch.setenv("STRAVA_ACCESS_TOKEN", "test-access")


def _make_activity(**kwargs) -> dict:
    """Minimal Strava activity dict with required fields."""
    base = {
        "id": 1,
        "type": "Run",
        "start_date_local": "2024-01-15T08:00:00",
        "distance": 5000.0,
        "moving_time": 1500,
        "average_heartrate": 150.0,
    }
    base.update(kwargs)
    return base


def test_normalize_computes_efficiency_factor():
    """EF = (distance_m * 60 / duration_s) / avg_hr.
    5000m * 60 / 1500s = 200 m/min; 200 / 150 bpm = 1.333...
    """
    from ingestion.sources.strava import StravaSource

    source = StravaSource()
    records = source.normalize([_make_activity()])

    assert len(records) == 1
    assert records[0]["efficiency_factor"] == pytest.approx(200.0 / 150.0, rel=1e-6)


def test_normalize_efficiency_factor_null_when_no_heart_rate():
    """EF is None when average_heartrate is absent."""
    from ingestion.sources.strava import StravaSource

    source = StravaSource()
    records = source.normalize([_make_activity(average_heartrate=None)])

    assert records[0]["efficiency_factor"] is None


def test_normalize_efficiency_factor_null_when_zero_duration():
    """EF is None when moving_time is 0 (avoids division by zero)."""
    from ingestion.sources.strava import StravaSource

    source = StravaSource()
    records = source.normalize([_make_activity(moving_time=0)])

    assert records[0]["efficiency_factor"] is None
