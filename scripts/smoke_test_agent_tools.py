"""Smoke test for the agent data query tools.

Calls get_training_and_recovery and get_upcoming_sessions directly against the
real database and prints their output.

Usage:
    poetry run python -m scripts.smoke_test_agent_tools
"""

from agent.queries import get_training_and_recovery, get_upcoming_sessions
from db.client import get_connection


def main() -> None:
    print("=== Agent Data Tools Smoke Test ===\n")

    with get_connection() as conn:
        print("--- get_training_and_recovery (last 7 days) ---")
        result = get_training_and_recovery(conn, lookback_days=7)
        print(result)

        print("\n--- get_upcoming_sessions (next 7 days) ---")
        result = get_upcoming_sessions(conn, days_ahead=7)
        print(result)

        print("\n--- guard: get_training_and_recovery (91 days, should return error) ---")
        result = get_training_and_recovery(conn, lookback_days=91)
        print(result)

    print("\n=== Smoke test complete ===")


if __name__ == "__main__":
    main()
