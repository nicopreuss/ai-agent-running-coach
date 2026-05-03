"""Smoke test: full Whoop ingest pipeline — fetch → normalize → upsert → verify in Supabase."""

from sqlalchemy import text

from db.client import get_connection
from ingestion.sources.whoop import WhoopSource


def main() -> None:
    # 1. Count existing rows before ingest
    with get_connection() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM whoop_recovery_daily")).scalar()
    print(f"Recovery rows in DB before ingest: {before}")

    # 2. Run pipeline
    source = WhoopSource()

    print("\nFetching from Whoop...")
    raw = source.fetch()
    print(f"  Fetched {len(raw)} raw daily records")

    records = source.normalize(raw)
    print(f"  Normalised {len(records)} records")

    inserted = source.upsert(records)
    skipped = len(records) - inserted
    print(f"  Inserted {inserted} new records  ({skipped} already existed, skipped)")

    # 3. Query DB to confirm rows are there
    with get_connection() as conn:
        after = conn.execute(text("SELECT COUNT(*) FROM whoop_recovery_daily")).scalar()
        sample = conn.execute(
            text(
                "SELECT date, recovery_score, hrv_rmssd_ms, resting_heart_rate, sleep_duration_ms "
                "FROM whoop_recovery_daily ORDER BY date DESC LIMIT 5"
            )
        ).fetchall()

    print(f"\nRecovery rows in DB after ingest: {after}")
    print("\nMost recent 5 days:")
    for row in sample:
        sleep_h = f"{(row.sleep_duration_ms or 0) / 3_600_000:.1f}h"
        hr = f"HRV={row.hrv_rmssd_ms:.1f}ms" if row.hrv_rmssd_ms else "HRV=n/a"
        print(
            f"  {row.date}  recovery={row.recovery_score or 'n/a':>5}%  "
            f"{hr}  RHR={row.resting_heart_rate or 'n/a'}bpm  sleep={sleep_h}"
        )


if __name__ == "__main__":
    main()
