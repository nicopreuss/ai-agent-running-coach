"""Smoke test: fetch and display Runna sessions from Google Calendar."""

from ingestion.sources.google_calendar import (
    GoogleCalendarSource,
    _PLAN_END_DATE,
    _PLAN_START_DATE,
)


def main() -> None:
    print("Connecting to Google Calendar...")
    source = GoogleCalendarSource()

    raw = source.fetch()
    print(
        f"Fetched {len(raw)} total events from calendar "
        f"({_PLAN_START_DATE} → {_PLAN_END_DATE})."
    )

    normalised = source.normalize(raw)
    print(f"Found {len(normalised)} Runna sessions.")

    for session in normalised[:5]:
        print(f"  {session['date']} — {session['title']}")
        if session["runna_url"]:
            print(f"    {session['runna_url']}")

    if len(normalised) > 5:
        print(f"  ... and {len(normalised) - 5} more.")

    inserted = source.upsert(normalised)
    print(f"Upserted: {inserted} new rows inserted.")


if __name__ == "__main__":
    main()
