"""Smoke test for the athlete profile and session notes memory system.

Writes test entries to the real Supabase DB, reads them back, and prints a summary.
Run with: poetry run python -m scripts.smoke_test_athlete_memory
"""

from agent.memory import add_session_note, load_athlete_context, update_athlete_profile


def main() -> None:
    print("=== Athlete Memory Smoke Test ===\n")

    print("1. Loading current athlete context...")
    context = load_athlete_context()
    print(context[:600] if len(context) > 600 else context)
    print()

    print("2. Writing test fact to athlete profile...")
    result = update_athlete_profile("[SMOKE TEST] This entry verifies profile writes work")
    print(f"   {result}")
    print()

    print("3. Adding a session note for today...")
    result = add_session_note("[SMOKE TEST] Verifying session note writes work")
    print(f"   {result}")
    print()

    print("4. Reloading context to verify both writes are visible...")
    context = load_athlete_context()
    smoke_ok = "[SMOKE TEST]" in context
    status = "PASS" if smoke_ok else "FAIL"
    print(f"   {status} — smoke test entries {'found' if smoke_ok else 'NOT found'} in context.")
    print()
    print(context[:1200] if len(context) > 1200 else context)
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
