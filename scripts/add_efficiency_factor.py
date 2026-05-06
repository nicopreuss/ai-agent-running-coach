"""One-time idempotent migration: add efficiency_factor to strava_activities."""

from sqlalchemy import text

from db.client import get_connection


def add_efficiency_factor() -> dict:
    """Add efficiency_factor column and backfill existing rows.

    Safe to re-run: ADD COLUMN IF NOT EXISTS skips the ALTER when the column
    already exists; UPDATE WHERE efficiency_factor IS NULL skips filled rows.
    """
    with get_connection() as conn:
        conn.execute(
            text(
                "ALTER TABLE strava_activities "
                "ADD COLUMN IF NOT EXISTS efficiency_factor FLOAT"
            )
        )
        conn.commit()

        result = conn.execute(
            text(
                """
                UPDATE strava_activities
                SET efficiency_factor = (distance_meters * 60.0 / duration_seconds) / avg_heart_rate
                WHERE avg_heart_rate IS NOT NULL
                  AND duration_seconds > 0
                  AND distance_meters > 0
                  AND efficiency_factor IS NULL
                """
            )
        )
        conn.commit()
        return {"updated": result.rowcount}


def main() -> None:
    result = add_efficiency_factor()
    print(f"Backfilled {result['updated']} rows with efficiency_factor.")


if __name__ == "__main__":
    main()
