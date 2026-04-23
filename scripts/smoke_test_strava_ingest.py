"""Smoke test: full Strava ingest pipeline — fetch → normalize → upsert → verify in Supabase."""

from sqlalchemy import text

from db.client import get_connection
from ingestion.sources.strava import StravaSource


def main() -> None:
    # 1. Count existing rows before ingest
    with get_connection() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM strava_activities")).scalar()
    print(f"Strava activities in DB before ingest: {before}")

    # 2. Run pipeline
    source = StravaSource()

    print("\nFetching from Strava...")
    raw = source.fetch()
    print(f"  Fetched {len(raw)} raw runs")

    records = source.normalize(raw)
    print(f"  Normalised {len(records)} records")

    inserted = source.upsert(records)
    skipped = len(records) - inserted
    print(f"  Inserted {inserted} new records  ({skipped} already existed, skipped)")

    # 3. Query DB to confirm rows are there
    with get_connection() as conn:
        after = conn.execute(text("SELECT COUNT(*) FROM strava_activities")).scalar()
        sample = conn.execute(
            text(
                "SELECT date, name, distance_meters, avg_heart_rate "
                "FROM strava_activities ORDER BY date DESC LIMIT 5"
            )
        ).fetchall()

    print(f"\nStrava activities in DB after ingest: {after}")
    print("\nMost recent 5 runs:")
    for row in sample:
        km = (row.distance_meters or 0) / 1000
        hr = f"HR: {row.avg_heart_rate:.0f}" if row.avg_heart_rate else "HR: n/a"
        print(f"  {row.date}  {str(row.name):<35}  {km:.2f} km  {hr}")


if __name__ == "__main__":
    main()
