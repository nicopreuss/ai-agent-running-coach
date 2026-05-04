from db.models import GoogleCalendarRunnaSession


def test_gcal_table_name():
    assert GoogleCalendarRunnaSession.__tablename__ == "google_calendar_runna_sessions"


def test_gcal_has_required_columns():
    cols = {c.key for c in GoogleCalendarRunnaSession.__table__.columns}
    assert cols >= {"google_event_id", "date", "title", "description", "runna_url", "created_at"}


def test_gcal_primary_key_is_event_id():
    pk_cols = {c.key for c in GoogleCalendarRunnaSession.__table__.primary_key}
    assert pk_cols == {"google_event_id"}
