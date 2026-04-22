"""Application entry point.

Run the agent interactively from the command line, or swap out the loop
below to trigger an ingestion pipeline, a scheduled job, etc.
"""

import logging

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Start an interactive REPL that passes user input to the agent."""
    from agent.agent import run

    print("Agent ready. Type 'exit' or Ctrl-C to quit.\n")

    while True:
        try:
            query = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            break

        response = run(query)
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    main()
