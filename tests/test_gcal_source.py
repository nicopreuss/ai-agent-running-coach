from datetime import date
from unittest.mock import MagicMock, patch

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


def test_normalize_excludes_events_before_plan_start():
    """Events dated before the training plan start date are always skipped."""
    desc = "📲 View in the Runna app: https://club.runna.com/n9Tx/workout?dayId=abc"
    raw = [
        {
            "id": "evt_old",
            "summary": "Easy Run",
            "description": desc,
            "start": {"date": "2026-02-28"},  # one day before plan start
        }
    ]
    assert _make_source().normalize(raw) == []


def test_normalize_includes_event_on_plan_start_date():
    """Events on exactly the plan start date are included."""
    desc = "📲 View in the Runna app: https://club.runna.com/n9Tx/workout?dayId=abc"
    raw = [
        {
            "id": "evt_start",
            "summary": "Easy Run",
            "description": desc,
            "start": {"date": "2026-03-02"},
        }
    ]
    result = _make_source().normalize(raw)
    assert len(result) == 1
    assert result[0]["google_event_id"] == "evt_start"


def test_normalize_excludes_strava_synced_past_events():
    """Past events with activityId=strava- in the Runna URL are Strava-synced runs — skipped."""
    desc = (
        "📊 Summary:\nTime: 46:29\n\n"
        "📲 View in the Runna app: "
        "https://club.runna.com/n9Tx/activities?activityId=strava-17543720068"
    )
    raw = [
        {
            "id": "evt_strava",
            "summary": "Morning Run",
            "description": desc,
            "start": {"date": "2026-04-26"},
        }
    ]
    assert _make_source().normalize(raw) == []


def test_normalize_keeps_garmin_completed_runna_event():
    """Past events with activityId=garmin- are Runna sessions completed via Garmin — kept."""
    desc = (
        "📊 Summary:\nDistance: 5.01km\n\n"
        "📲 View in the Runna app: "
        "https://club.runna.com/n9Tx/activities?activityId=garmin-22037458934"
    )
    raw = [
        {
            "id": "evt_garmin",
            "summary": "5km Easy Run",
            "description": desc,
            "start": {"date": "2026-03-02"},
        }
    ]
    result = _make_source().normalize(raw)
    assert len(result) == 1
    assert result[0]["google_event_id"] == "evt_garmin"


def test_normalize_future_events_bypass_strava_filter():
    """Future events are planned sessions by definition — strava URL check is skipped."""
    # Construct a date guaranteed to be in the future
    from datetime import date, timedelta

    future_date = (date.today() + timedelta(days=10)).isoformat()
    # Even if the URL looked strava-like, a future event should be kept.
    desc = (
        "📲 View in the Runna app: "
        "https://club.runna.com/n9Tx/workout?dayId=future-session-123"
    )
    raw = [
        {
            "id": "evt_future",
            "summary": "Long Run",
            "description": desc,
            "start": {"date": future_date},
        }
    ]
    result = _make_source().normalize(raw)
    assert len(result) == 1
    assert result[0]["google_event_id"] == "evt_future"


def test_token_refresh_sends_readonly_scope():
    source = _make_source()
    source._expires_at = 0

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "new_token", "expires_in": 3600}

    with patch(
        "ingestion.sources.google_calendar.requests.post", return_value=mock_resp
    ) as mock_post:
        source._do_token_refresh()

    posted_data = mock_post.call_args.kwargs["data"]
    assert "calendar.readonly" in posted_data["scope"]
    assert source._access_token == "new_token"


def test_fetch_paginates_correctly():
    source = _make_source()

    page1 = {"items": [{"id": "evt1"}], "nextPageToken": "tok123"}
    page2 = {"items": [{"id": "evt2"}]}

    mock_r1, mock_r2 = MagicMock(), MagicMock()
    mock_r1.json.return_value = page1
    mock_r2.json.return_value = page2

    with patch(
        "ingestion.sources.google_calendar.requests.get", side_effect=[mock_r1, mock_r2]
    ):
        result = source.fetch()

    assert len(result) == 2
    assert result[0]["id"] == "evt1"
    assert result[1]["id"] == "evt2"
