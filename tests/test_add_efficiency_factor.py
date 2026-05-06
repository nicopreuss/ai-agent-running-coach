"""Tests for scripts/add_efficiency_factor.py."""

from unittest.mock import MagicMock, patch


def _patch_conn(mock_conn: MagicMock):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=mock_conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return patch("scripts.add_efficiency_factor.get_connection", return_value=ctx)


def test_add_efficiency_factor_executes_alter_and_backfill():
    """Both the ALTER TABLE and the UPDATE backfill must be executed and committed."""
    mock_conn = MagicMock()
    mock_conn.execute.return_value.rowcount = 5

    with _patch_conn(mock_conn):
        from scripts.add_efficiency_factor import add_efficiency_factor
        result = add_efficiency_factor()

    assert mock_conn.execute.call_count == 2
    assert mock_conn.commit.call_count == 2

    first_sql = str(mock_conn.execute.call_args_list[0][0][0])
    assert "ALTER TABLE" in first_sql
    assert "efficiency_factor" in first_sql

    second_sql = str(mock_conn.execute.call_args_list[1][0][0])
    assert "UPDATE" in second_sql
    assert "efficiency_factor" in second_sql
    assert "avg_heart_rate" in second_sql

    assert result == {"updated": 5}


def test_add_efficiency_factor_returns_zero_when_no_rows_to_backfill():
    """Returns {"updated": 0} when no rows need backfilling."""
    mock_conn = MagicMock()
    mock_conn.execute.return_value.rowcount = 0

    with _patch_conn(mock_conn):
        from scripts.add_efficiency_factor import add_efficiency_factor
        result = add_efficiency_factor()

    assert result == {"updated": 0}
