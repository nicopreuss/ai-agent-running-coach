"""Utility script to clear one or more tables in the database.

Usage:
    # Clear specific tables:
    poetry run python -m scripts.clear_tables athlete_profile session_notes

    # Clear all tables:
    poetry run python -m scripts.clear_tables
"""

import sys

from sqlalchemy import text

from db.client import get_connection
from db.models import Base

_ALL_TABLES = list(Base.metadata.tables.keys())


def main() -> None:
    requested = sys.argv[1:]
    tables = requested if requested else _ALL_TABLES

    unknown = [t for t in tables if t not in _ALL_TABLES]
    if unknown:
        print(f"Unknown tables: {unknown}")
        print(f"Available: {_ALL_TABLES}")
        sys.exit(1)

    with get_connection() as conn:
        for table in tables:
            conn.execute(text(f"DELETE FROM {table}"))  # noqa: S608 — table name validated above
            print(f"  Cleared: {table}")
        conn.commit()

    print("Done.")


if __name__ == "__main__":
    main()
