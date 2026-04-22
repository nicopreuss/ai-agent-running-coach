"""Evaluation runner: loads golden_set.json and scores agent responses."""

import json
import sys
from pathlib import Path

import agent.agent as agent_module

GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.json"


def run_evals() -> None:
    """Run every question in the golden set and print a pass/fail per entry."""
    with GOLDEN_SET_PATH.open() as f:
        golden_set: list[dict] = json.load(f)

    passed = 0
    failed = 0

    for i, entry in enumerate(golden_set, start=1):
        question: str = entry["question"]
        expected: str = entry["expected_answer"]
        notes: str = entry.get("notes", "")

        actual = agent_module.run(question)

        # REPLACE: swap this simple substring check for a more robust matcher
        # (e.g. LLM-as-judge, embedding similarity, or exact-match normalisation)
        ok = expected.strip().lower() in actual.strip().lower()

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"[{i:02d}] {status}  | {notes}")
        if not ok:
            print(f"       expected: {expected!r}")
            print(f"       actual  : {actual!r}")

    total = passed + failed
    print(f"\nResults: {passed}/{total} passed")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    run_evals()
