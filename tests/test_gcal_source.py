from datetime import date

from ingestion.sources.google_calendar import GoogleCalendarSource


def _make_source() -> GoogleCalendarSource:
    """Instantiate without calling __init__ (which reads env vars)."""
    source = GoogleCalendarSource.__new__(GoogleCalendarSource)
    source._client_id = "fake_id"
    source._client_secret = "fake_secret"
    source._refresh_token = "fake_token"
    source._calendar_id = "fake_cal"
    source._access_token = "fake_access"
    source._expires_at = float("inf")
    return source


def test_normalize_filters_non_runna_events():
    raw = [
        {
            "id": "abc",
            "summary": "Dentist",
            "description": "No runna here",
            "start": {"date": "2026-05-10"},
        }
    ]
    assert _make_source().normalize(raw) == []


def test_normalize_extracts_runna_event():
    desc = (
        "Easy run\n📲 View in the Runna app: "
        "https://club.runna.com/n9Tx/workout?dayId=abc123"
    )
    raw = [
        {
            "id": "evt1",
            "summary": "Easy 5k",
            "description": desc,
            "start": {"date": "2026-05-10"},
        }
    ]
    result = _make_source().normalize(raw)
    assert len(result) == 1
    assert result[0]["google_event_id"] == "evt1"
    assert result[0]["title"] == "Easy 5k"
    assert result[0]["description"] == desc
    assert result[0]["runna_url"] == "https://club.runna.com/n9Tx/workout?dayId=abc123"
    assert result[0]["date"] == date(2026, 5, 10)


def test_normalize_handles_timed_event():
    desc = "📲 View in the Runna app: https://club.runna.com/abc"
    raw = [
        {
            "id": "evt2",
            "summary": "Tempo",
            "description": desc,
            "start": {"dateTime": "2026-05-10T07:00:00+02:00"},
        }
    ]
    result = _make_source().normalize(raw)
    assert result[0]["date"] == date(2026, 5, 10)


def test_normalize_empty_input():
    assert _make_source().normalize([]) == []


def test_normalize_skips_event_with_no_description():
    raw = [{"id": "evt3", "summary": "No desc", "start": {"date": "2026-05-10"}}]
    assert _make_source().normalize(raw) == []
