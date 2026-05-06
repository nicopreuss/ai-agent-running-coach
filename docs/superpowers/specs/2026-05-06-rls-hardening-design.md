# RLS Hardening — Design Spec

**Date:** 2026-05-06
**Status:** Approved

## Problem

Supabase's security linter flags all tables in the `public` schema as a risk because Row Level
Security (RLS) is not enabled. Without RLS, any table reachable via the Supabase Data API
(PostgREST) can be read by the `anon` role with no row-level protection.

The app connects via a direct `postgresql://` connection string (SQLAlchemy), not through
PostgREST, so there is no active exploit. The fix is nonetheless worth applying: it silences
the linter, closes the PostgREST surface defensively, and costs nothing at runtime.

## Chosen approach: enable RLS with no policies

`ALTER TABLE <table> ENABLE ROW LEVEL SECURITY` on every table. No explicit policies are added.
Postgres's default when RLS is enabled with no policies is **deny all** for non-superuser roles
(`anon`, `authenticated`). The `DATABASE_URL` connects as `postgres` or `service_role`, both of
which bypass RLS entirely — zero runtime impact on the app.

## Component: `scripts/enable_rls.py`

A one-time idempotent migration script following the same pattern as `scripts/create_tables.py`.

### Table discovery

Reads table names from `Base.metadata.tables` — the same SQLAlchemy metadata registry used by
`create_tables.py`. Any model added to `db/models.py` in the future is automatically picked up
without touching this script.

### Idempotency

Before issuing `ALTER TABLE`, the script queries `pg_class` to check whether RLS is already
enabled (`relrowsecurity = true`). Tables that already have RLS enabled are skipped and reported
as such. Safe to re-run at any time.

### Execution

Each `ALTER TABLE <name> ENABLE ROW LEVEL SECURITY` is executed via `sqlalchemy.text()` over
a direct connection obtained from `db.client.get_connection()`. Each statement is committed
immediately so a failure on one table does not roll back earlier successes.

### Output

Human-readable per-table result, then a summary line:

```
strava_activities             → enabled
whoop_recovery_daily          → enabled
ingestion_log                 → already enabled (skipped)
google_calendar_runna_sessions → enabled
athlete_profile               → enabled
session_notes                 → enabled

Done. 5 enabled, 1 skipped.
```

### Run command

```
poetry run python -m scripts.enable_rls
```

## Out of scope

- Adding RLS policies (not needed — the app never goes through PostgREST)
- Revoking `anon` from the public schema (Option B — overkill for a single-user project)
- Automating this in `create_tables.py` — kept separate so each script has one clear purpose
