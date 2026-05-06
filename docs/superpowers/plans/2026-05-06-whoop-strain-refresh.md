# Whoop Strain Live Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two bugs so that clicking "Refresh All" always fetches and stores today's latest Whoop `daily_strain` value.

**Architecture:** Two targeted changes — clamp the Whoop watermark to `min(watermark, start_of_today_utc)` in `pipeline.py` so today's cycle is always re-fetched, and switch the upsert in `whoop.py` from `ON CONFLICT DO NOTHING` to `ON CONFLICT DO UPDATE SET daily_strain = ... WHERE date = today` so today's strain is overwritten while all historical rows remain immutable.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 (`insert`, `on_conflict_do_update`), `unittest.mock`, pytest.

---

## File Map

| Action | Path | Change |
|--------|------|--------|
| Modify | `ingestion/pipeline.py:1-6,75-77` | Add `date, time` imports; clamp Whoop watermark |
| Modify | `ingestion/sources/whoop.py:1-6,154-167` | Add `date` import; switch to conditional `on_conflict_do_update` |
| Modify | `tests/test_pipeline.py` | Add 2 tests for watermark clamping |
| Modify | `tests/test_whoop_normalize.py` | Add 2 tests for new upsert behaviour |

---

## Task 1: Watermark floor — pipeline.py

**Files:**
- Modify: `ingestion/pipeline.py:5` (imports)
- Modify: `ingestion/pipeline.py:75-77` (Whoop branch inside `run()`)
- Modify: `tests/test_pipeline.py` (add 2 tests)

### Step 1: Write the two failing tests

Add these tests to the bottom of `tests/test_pipeline.py`:

```python
def test_run_whoop_clamps_start_date_to_today_when_watermark_is_later_today():
    """Watermark later in the day must be clamped to 00:00:00 today."""
    from datetime import date, time, timedelta

    today = date.today()
    # Simulate a watermark set at 14:00 today (after this morning's cycle started)
    watermark = datetime.combine(today, time(14, 0, 0)).replace(tzinfo=timezone.utc)
    expected_start = datetime.combine(today, time.min).replace(tzinfo=timezone.utc)
    expected_str = expected_start.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    mock_source = MagicMock()
    mock_source.fetch.return_value = []
    mock_source.normalize.return_value = []
    mock_source.upsert.return_value = 0
    captured = {}

    def capture(start_date=None):
        captured["start_date"] = start_date
        return mock_source

    with patch("ingestion.pipeline._read_watermark", return_value=watermark), \
         patch("ingestion.pipeline.WhoopSource", side_effect=capture), \
         patch("ingestion.pipeline._write_log"):
        run("whoop")

    assert captured["start_date"] == expected_str


def test_run_whoop_uses_watermark_unchanged_when_before_today():
    """Watermark from a previous day must be used as-is (no clamping)."""
    from datetime import date, timedelta

    yesterday = date.today() - timedelta(days=1)
    watermark = datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=timezone.utc)
    expected_str = watermark.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    mock_source = MagicMock()
    mock_source.fetch.return_value = []
    mock_source.normalize.return_value = []
    mock_source.upsert.return_value = 0
    captured = {}

    def capture(start_date=None):
        captured["start_date"] = start_date
        return mock_source

    with patch("ingestion.pipeline._read_watermark", return_value=watermark), \
         patch("ingestion.pipeline.WhoopSource", side_effect=capture), \
         patch("ingestion.pipeline._write_log"):
        run("whoop")

    assert captured["start_date"] == expected_str
```

### Step 2: Run the new tests to confirm they fail

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_pipeline.py::test_run_whoop_clamps_start_date_to_today_when_watermark_is_later_today tests/test_pipeline.py::test_run_whoop_uses_watermark_unchanged_when_before_today -v
```

Expected: both FAIL (the watermark clamping logic doesn't exist yet).

### Step 3: Implement the watermark floor

**`ingestion/pipeline.py` — update the import line (line 5):**

```python
from datetime import date, datetime, time, timezone
```

**`ingestion/pipeline.py` — replace lines 75-77 (the `elif source_name == "whoop":` block):**

```python
    elif source_name == "whoop":
        if watermark:
            today_start = datetime.combine(date.today(), time.min).replace(tzinfo=timezone.utc)
            effective = min(watermark, today_start)
            start_date = effective.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        else:
            start_date = None
        source = WhoopSource(start_date=start_date)
```

### Step 4: Run the new tests to confirm they pass

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_pipeline.py::test_run_whoop_clamps_start_date_to_today_when_watermark_is_later_today tests/test_pipeline.py::test_run_whoop_uses_watermark_unchanged_when_before_today -v
```

Expected: both PASS.

### Step 5: Run the full pipeline test suite

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_pipeline.py -v
```

Expected: all tests pass (including the 6 pre-existing ones).

### Step 6: Commit

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && git add ingestion/pipeline.py tests/test_pipeline.py && git commit -m "fix: clamp Whoop watermark to start of today so today's cycle is always re-fetched"
```

---

## Task 2: Conditional upsert — whoop.py

**Files:**
- Modify: `ingestion/sources/whoop.py:5` (imports)
- Modify: `ingestion/sources/whoop.py:154-167` (the `upsert()` method)
- Modify: `tests/test_whoop_normalize.py` (add 2 tests)

### Step 1: Write the two failing tests

Add these tests to the bottom of `tests/test_whoop_normalize.py`:

```python
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
```

### Step 2: Run the new tests to confirm they fail

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_whoop_normalize.py::test_upsert_calls_on_conflict_do_update_for_daily_strain tests/test_whoop_normalize.py::test_upsert_returns_zero_and_skips_db_for_empty_records -v
```

Expected: `test_upsert_calls_on_conflict_do_update_for_daily_strain` FAILS (currently calls `on_conflict_do_nothing`). `test_upsert_returns_zero_and_skips_db_for_empty_records` may PASS (the early return already exists) — that's fine.

### Step 3: Implement the conditional upsert

**`ingestion/sources/whoop.py` — update the import line (line 5):**

```python
from datetime import date, datetime
```

**`ingestion/sources/whoop.py` — replace the entire `upsert()` method (lines 154-167):**

```python
    def upsert(self, records: list[dict]) -> int:
        """Insert recovery records.

        Historical rows (date != today) are skipped on conflict.
        Today's row has its daily_strain refreshed on conflict.
        """
        if not records:
            return 0

        with get_connection() as conn:
            ins = insert(WhoopRecoveryDaily).values(records)
            stmt = ins.on_conflict_do_update(
                index_elements=["whoop_cycle_id"],
                set_={"daily_strain": ins.excluded.daily_strain},
                where=(WhoopRecoveryDaily.date == date.today()),
            )
            result = conn.execute(stmt)
            conn.commit()
            return result.rowcount
```

### Step 4: Run the new tests to confirm they pass

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_whoop_normalize.py::test_upsert_calls_on_conflict_do_update_for_daily_strain tests/test_whoop_normalize.py::test_upsert_returns_zero_and_skips_db_for_empty_records -v
```

Expected: both PASS.

### Step 5: Run the full whoop test suite

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest tests/test_whoop_normalize.py -v
```

Expected: all tests pass (including the 7 pre-existing ones).

### Step 6: Run the full test suite for regressions

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && poetry run pytest --tb=short -q
```

Expected: all tests pass.

### Step 7: Commit

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && git add ingestion/sources/whoop.py tests/test_whoop_normalize.py && git commit -m "fix: update daily_strain for today's row on Whoop upsert conflict"
```

---

## Task 3: Push and raise PR

- [ ] **Step 1: Push the branch**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && git push -u origin $(git branch --show-current)
```

- [ ] **Step 2: Create the PR**

```bash
cd /Users/nicolaspreuss/Documents/DataExpert/Projects/RunningCoach/ai-agent-running-coach && gh pr create \
  --title "fix: refresh daily_strain on Whoop re-ingest" \
  --body "$(cat <<'EOF'
## Summary

Fixes two bugs that together prevented today's Whoop strain from updating on refresh:

- **Watermark bug** (`pipeline.py`): the Whoop API filters cycles by start time. After a successful run the watermark advances past when today's cycle started (e.g. 6am cycle, 9am watermark). Clamp the Whoop start_date to \`min(watermark, start_of_today_utc)\` so today's cycle is always in the fetch window.
- **Upsert bug** (`whoop.py`): \`ON CONFLICT DO NOTHING\` meant today's strain was frozen at first-insert value. Switch to \`ON CONFLICT DO UPDATE SET daily_strain = EXCLUDED.daily_strain WHERE date = today\` so only today's strain is refreshed; all historical rows remain immutable.

## Test plan

- [ ] All new and existing tests pass
- [ ] Hit \"Refresh All\" in the UI during the day — dashboard strain updates to current value
- [ ] Verify historical rows in \`whoop_recovery_daily\` are unchanged after refresh

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
