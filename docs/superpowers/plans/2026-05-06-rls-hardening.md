# RLS Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `scripts/enable_rls.py` — a one-time idempotent migration that enables Row Level Security on every table registered in `db/models.py`, silencing Supabase's security linter with zero runtime impact.

**Architecture:** The script reads table names dynamically from `Base.metadata.tables` (same registry used by `create_tables.py`), checks `pg_class.relrowsecurity` for each table to skip already-enabled ones, then runs `ALTER TABLE <name> ENABLE ROW LEVEL SECURITY` for the rest. Each statement is committed immediately so a failure on one table does not roll back earlier successes.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 (`text()`), `unittest.mock` for tests, pytest.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `scripts/enable_rls.py` | Migration logic: discover tables, check RLS status, run ALTER TABLE |
| Create | `tests/test_enable_rls.py` | Unit tests for `_rls_enabled()` and `enable_rls()` |

---

## Task 1: Write and run failing tests

**Files:**
- Create: `tests/test_enable_rls.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for scripts/enable_rls.py."""

from unittest.mock import MagicMock, patch


def _make_conn_mock() -> MagicMock:
    return MagicMock()


def _patch_conn(mock_conn: MagicMock):
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
poetry run pytest tests/test_enable_rls.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.enable_rls'` (or similar import error) — confirms the tests are wired correctly and the implementation doesn't exist yet.

---

## Task 2: Implement `scripts/enable_rls.py`

**Files:**
- Create: `scripts/enable_rls.py`

- [ ] **Step 1: Write the implementation**

```python
"""One-time migration: enable Row Level Security on all tables in db/models.py."""

from sqlalchemy import text

from db.client import get_connection
from db.models import Base


def _rls_enabled(conn, table_name: str) -> bool:
    """Return True if RLS is already enabled on *table_name* in pg_class."""
    row = conn.execute(
        text("SELECT relrowsecurity FROM pg_class WHERE relname = :name"),
        {"name": table_name},
    ).fetchone()
    return bool(row and row.relrowsecurity)


def enable_rls() -> dict[str, str]:
    """Enable RLS on every table registered in Base.metadata.

    Returns a dict mapping each table name to "enabled" or "skipped".
    Table names come from code-controlled metadata, not user input — the
    f-string interpolation below is intentional and safe.
    """
    results: dict[str, str] = {}
    with get_connection() as conn:
        for table_name in Base.metadata.tables:
            if _rls_enabled(conn, table_name):
                results[table_name] = "skipped"
            else:
                conn.execute(
                    text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")  # noqa: S608
                )
                conn.commit()
                results[table_name] = "enabled"
    return results


def main() -> None:
    results = enable_rls()
    for table, status in results.items():
        marker = "→ enabled" if status == "enabled" else "→ already enabled (skipped)"
        print(f"{table:<45} {marker}")
    enabled = sum(1 for s in results.values() if s == "enabled")
    skipped = len(results) - enabled
    print(f"\nDone. {enabled} enabled, {skipped} skipped.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run tests to confirm they pass**

```bash
poetry run pytest tests/test_enable_rls.py -v
```

Expected output:
```
tests/test_enable_rls.py::test_rls_enabled_returns_true_when_pg_class_says_yes PASSED
tests/test_enable_rls.py::test_rls_enabled_returns_false_when_pg_class_says_no PASSED
tests/test_enable_rls.py::test_rls_enabled_returns_false_when_table_not_in_pg_class PASSED
tests/test_enable_rls.py::test_enable_rls_issues_alter_table_for_unenabled_table PASSED
tests/test_enable_rls.py::test_enable_rls_skips_already_enabled_table PASSED
tests/test_enable_rls.py::test_enable_rls_returns_mixed_results PASSED
6 passed
```

- [ ] **Step 3: Run the full test suite to check for regressions**

```bash
poetry run pytest --tb=short -q
```

Expected: all existing tests continue to pass alongside the 6 new ones.

- [ ] **Step 4: Verify the script runs locally (manual)**

```bash
poetry run python -m scripts.enable_rls
```

Expected output (exact table names may vary as new tables are added):
```
strava_activities                              → enabled
whoop_recovery_daily                           → enabled
ingestion_log                                  → enabled
google_calendar_runna_sessions                 → enabled
athlete_profile                                → enabled
session_notes                                  → enabled

Done. 6 enabled, 0 skipped.
```

On a second run all rows should show `→ already enabled (skipped)` and `Done. 0 enabled, 6 skipped.`

- [ ] **Step 5: Commit**

```bash
git add scripts/enable_rls.py tests/test_enable_rls.py
git commit -m "feat: add enable_rls migration script with dynamic table discovery"
```

---

## Task 3: Push and raise PR

- [ ] **Step 1: Push the branch**

```bash
git push -u origin $(git branch --show-current)
```

- [ ] **Step 2: Create the PR**

```bash
gh pr create \
  --title "feat: add enable_rls migration script" \
  --body "Adds scripts/enable_rls.py — enables RLS on all tables in Base.metadata to silence the Supabase security linter. Dynamic discovery means new tables are covered automatically. Idempotent: tables with RLS already enabled are skipped."
```
