"""Tests for agent/memory.py."""

from unittest.mock import MagicMock, patch

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


def _make_conn_mock(execute_side_effects: list) -> MagicMock:
    """Return a mock connection whose execute() calls return successive values."""
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = execute_side_effects
    return mock_conn


def _patch_conn(mock_conn: MagicMock):
    """Patch get_connection() to return mock_conn as a context manager."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=mock_conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return patch("agent.memory.get_connection", return_value=ctx)


# --- load_athlete_context ---

def test_load_athlete_context_returns_onboarding_when_no_profile() -> None:
    mock_conn = _make_conn_mock([
        MagicMock(**{"fetchone.return_value": None}),   # profile query
        MagicMock(**{"fetchall.return_value": []}),     # notes query (never reached)
    ])

    with _patch_conn(mock_conn):
        from agent.memory import load_athlete_context
        result = load_athlete_context()

    assert "First-Run Onboarding" in result
    assert "How long have you been running" in result


def test_load_athlete_context_returns_onboarding_when_content_empty() -> None:
    profile_row = MagicMock()
    profile_row.content = ""

    mock_conn = _make_conn_mock([
        MagicMock(**{"fetchone.return_value": profile_row}),
        MagicMock(**{"fetchall.return_value": []}),
    ])

    with _patch_conn(mock_conn):
        from agent.memory import load_athlete_context
        result = load_athlete_context()

    assert "First-Run Onboarding" in result


def test_load_athlete_context_returns_profile_and_notes() -> None:
    profile_row = MagicMock()
    profile_row.content = "Goal: Paris Marathon sub-4h"

    note_row = MagicMock()
    note_row.content = "- [10:00 UTC] felt fatigued after long run"

    mock_conn = _make_conn_mock([
        MagicMock(**{"fetchone.return_value": profile_row}),
        MagicMock(**{"fetchall.return_value": [note_row]}),
    ])

    with _patch_conn(mock_conn):
        from agent.memory import load_athlete_context
        result = load_athlete_context()

    assert "## Athlete Profile" in result
    assert "Paris Marathon" in result
    assert "## Recent Session Notes" in result
    assert "felt fatigued" in result


def test_load_athlete_context_omits_notes_section_when_no_notes() -> None:
    profile_row = MagicMock()
    profile_row.content = "Goal: Paris Marathon sub-4h"

    mock_conn = _make_conn_mock([
        MagicMock(**{"fetchone.return_value": profile_row}),
        MagicMock(**{"fetchall.return_value": []}),
    ])

    with _patch_conn(mock_conn):
        from agent.memory import load_athlete_context
        result = load_athlete_context()

    assert "## Athlete Profile" in result
    assert "## Recent Session Notes" not in result


# --- update_athlete_profile ---

def test_update_athlete_profile_returns_confirmation() -> None:
    mock_conn = _make_conn_mock([MagicMock()])  # single atomic upsert

    with _patch_conn(mock_conn):
        from agent.memory import update_athlete_profile
        result = update_athlete_profile("Goal: sub-4h marathon")

    assert "Saved to your profile" in result
    mock_conn.commit.assert_called_once()


def test_update_athlete_profile_commits_on_existing_profile() -> None:
    mock_conn = _make_conn_mock([MagicMock()])  # single atomic upsert

    with _patch_conn(mock_conn):
        from agent.memory import update_athlete_profile
        result = update_athlete_profile("I prefer morning runs")

    assert "Saved to your profile" in result
    mock_conn.commit.assert_called_once()


# --- add_session_note ---

def test_add_session_note_returns_confirmation() -> None:
    mock_conn = _make_conn_mock([MagicMock()])  # single atomic upsert

    with _patch_conn(mock_conn):
        from agent.memory import add_session_note
        result = add_session_note("athlete mentioned left calf tightness")

    assert "Session note saved" in result
    mock_conn.commit.assert_called_once()


def test_system_prompt_includes_memory_tool_instructions() -> None:
    from agent.prompts import SYSTEM_PROMPT
    assert "## Memory tools" in SYSTEM_PROMPT
    assert "update_athlete_profile" in SYSTEM_PROMPT
    assert "add_session_note" in SYSTEM_PROMPT
    assert "remember that" in SYSTEM_PROMPT.lower()
