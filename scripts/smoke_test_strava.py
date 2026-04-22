"""Smoke test: verify Strava API connection and inspect a sample of activities."""

from ingestion.sources.strava import StravaSource


def main() -> None:
    source = StravaSource()

    print("Fetching activities from Strava...")
    raw = source.fetch()
    print(f"  Total runs fetched: {len(raw)}")

    if not raw:
        print("No activities returned — check your tokens and scope.")
        return

    print("\nNormalising...")
    records = source.normalize(raw)
    print(f"  Normalised records: {len(records)}")

    print("\nMost recent 5 runs:")
    for r in records[:5]:
        distance_km = (r["distance_meters"] or 0) / 1000
        pace_s = r["avg_pace_sec_per_km"]
        pace_str = f"{int(pace_s // 60)}:{int(pace_s % 60):02d}/km" if pace_s else "n/a"
        print(
            f"  {r['date']}  {r['name']:<35}  "
            f"{distance_km:.2f} km  {pace_str}  "
            f"HR: {r['avg_heart_rate'] or 'n/a'}"
        )


if __name__ == "__main__":
    main()
