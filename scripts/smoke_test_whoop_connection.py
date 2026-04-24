"""Smoke test: verify Whoop API connection and token refresh."""

from ingestion.sources.whoop import WhoopSource


def main() -> None:
    source = WhoopSource()
    print("Testing Whoop API connection...")

    data = source._get("/recovery", params={"limit": 5})
    records = data.get("records", [])
    next_token = data.get("next_token")

    print(f"  Received {len(records)} recovery record(s)")
    print(f"  next_token present: {bool(next_token)}")
    print("\nMost recent recoveries:")
    for r in records:
        score = r.get("score") or {}
        cycle_id = r.get("cycle_id", "?")
        recovery = score.get("recovery_score", "n/a")
        hrv = score.get("hrv_rmssd_milli", "n/a")
        rhr = score.get("resting_heart_rate", "n/a")
        print(f"  cycle {cycle_id}  recovery={recovery}%  HRV={hrv}ms  RHR={rhr}bpm")

    print("\nConnection OK")


if __name__ == "__main__":
    main()
