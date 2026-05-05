"""Tests for agent/memory.py."""

from db.models import AthleteProfile, SessionNote


def test_athlete_profile_table_name() -> None:
    assert AthleteProfile.__tablename__ == "athlete_profile"


def test_athlete_profile_columns() -> None:
    cols = {c.name for c in AthleteProfile.__table__.columns}
    assert cols == {"id", "user_id", "content", "updated_at"}


def test_athlete_profile_user_id_is_unique() -> None:
    unique_cols = {
        col
        for constraint in AthleteProfile.__table__.constraints
        if hasattr(constraint, "columns")
        for col in constraint.columns.keys()
    }
    assert "user_id" in unique_cols


def test_session_note_table_name() -> None:
    assert SessionNote.__tablename__ == "session_notes"


def test_session_note_columns() -> None:
    cols = {c.name for c in SessionNote.__table__.columns}
    assert cols == {"id", "user_id", "date", "content", "updated_at"}


def test_session_note_has_user_id_date_unique_constraint() -> None:
    from sqlalchemy import UniqueConstraint
    constraints = [
        c for c in SessionNote.__table__.constraints
        if isinstance(c, UniqueConstraint)
    ]
    unique_col_sets = [
        frozenset(c.columns.keys()) for c in constraints
    ]
    assert frozenset({"user_id", "date"}) in unique_col_sets
