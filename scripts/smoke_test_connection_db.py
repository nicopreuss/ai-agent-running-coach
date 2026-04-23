"""Smoke test: verify the database connection is configured and reachable."""

from sqlalchemy import text

from db.client import get_connection


def main() -> None:
    print("Testing database connection...")
    with get_connection() as conn:
        row = conn.execute(
            text("SELECT current_database(), current_user, version()")
        ).fetchone()

    print(f"  Database : {row[0]}")
    print(f"  User     : {row[1]}")
    print(f"  Version  : {row[2][:60]}")
    print("Connection OK")


if __name__ == "__main__":
    main()
