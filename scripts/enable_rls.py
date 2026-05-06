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
    # get_connection() gives explicit commit control; get_engine() does not.
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
