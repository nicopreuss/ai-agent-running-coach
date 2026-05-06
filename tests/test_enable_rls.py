"""Tests for scripts/enable_rls.py."""

from unittest.mock import MagicMock, patch


def _make_conn_mock() -> MagicMock:
    return MagicMock()


def _patch_conn(mock_conn: MagicMock) -> MagicMock:
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=mock_conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return patch("scripts.enable_rls.get_connection", return_value=ctx)


# --- _rls_enabled ---

def test_rls_enabled_returns_true_when_pg_class_says_yes() -> None:
    mock_conn = _make_conn_mock()
    row = MagicMock()
    row.relrowsecurity = True
    mock_conn.execute.return_value.fetchone.return_value = row

    from scripts.enable_rls import _rls_enabled
    assert _rls_enabled(mock_conn, "strava_activities") is True


def test_rls_enabled_returns_false_when_pg_class_says_no() -> None:
    mock_conn = _make_conn_mock()
    row = MagicMock()
    row.relrowsecurity = False
    mock_conn.execute.return_value.fetchone.return_value = row

    from scripts.enable_rls import _rls_enabled
    assert _rls_enabled(mock_conn, "strava_activities") is False


def test_rls_enabled_returns_false_when_table_not_in_pg_class() -> None:
    mock_conn = _make_conn_mock()
    mock_conn.execute.return_value.fetchone.return_value = None

    from scripts.enable_rls import _rls_enabled
    assert _rls_enabled(mock_conn, "nonexistent_table") is False


# --- enable_rls ---

def test_enable_rls_issues_alter_table_for_unenabled_table() -> None:
    mock_conn = _make_conn_mock()
    tables = {"strava_activities": MagicMock()}

    with patch("scripts.enable_rls.Base.metadata.tables", tables):
        with patch("scripts.enable_rls._rls_enabled", return_value=False):
            with _patch_conn(mock_conn):
                from scripts.enable_rls import enable_rls
                results = enable_rls()

    assert results["strava_activities"] == "enabled"
    mock_conn.commit.assert_called_once()


def test_enable_rls_skips_already_enabled_table() -> None:
    mock_conn = _make_conn_mock()
    tables = {"strava_activities": MagicMock()}

    with patch("scripts.enable_rls.Base.metadata.tables", tables):
        with patch("scripts.enable_rls._rls_enabled", return_value=True):
            with _patch_conn(mock_conn):
                from scripts.enable_rls import enable_rls
                results = enable_rls()

    assert results["strava_activities"] == "skipped"
    mock_conn.commit.assert_not_called()


def test_enable_rls_returns_mixed_results() -> None:
    mock_conn = _make_conn_mock()
    tables = {
        "strava_activities": MagicMock(),
        "whoop_recovery_daily": MagicMock(),
    }

    def mock_rls_enabled(_conn, table_name: str) -> bool:
        return table_name == "strava_activities"

    with patch("scripts.enable_rls.Base.metadata.tables", tables):
        with patch("scripts.enable_rls._rls_enabled", side_effect=mock_rls_enabled):
            with _patch_conn(mock_conn):
                from scripts.enable_rls import enable_rls
                results = enable_rls()

    assert results["strava_activities"] == "skipped"
    assert results["whoop_recovery_daily"] == "enabled"
    assert mock_conn.commit.call_count == 1
