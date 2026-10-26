"""Run the trip planner on fixed routes as eval runs and check the results.

Each route runs as a Prefactor agent instance with the ``eval`` purpose. The
script exits with status 1 when any final plan fails its checks, so it can
run in CI.

Usage:
    python run_evals.py
"""

from __future__ import annotations

import asyncio
import sys

from main import run_trip

CASES = [
    "Plan a 4-day road trip from Melbourne to Adelaide. I like wine and the coast.",
    "Plan a 3-day road trip from San Francisco to Los Angeles. I like food.",
    "Plan a 3-day road trip from Lyon to Nice. I like history and markets.",
]


async def run_evals() -> bool:
    """Run every case in turn and print a summary.

    Returns:
        Whether every final plan passed.
    """
    all_passed = True
    for request in CASES:
        state = await run_trip(request, purpose="eval")
        quality = state["quality"]
        status = "pass" if quality["passed"] else "FAIL"
        print(
            f"{status}  {quality['score']:>3}/100  attempt {quality['attempt']}  "
            f"{request}"
        )
        for check in quality["checks"]:
            if not check["passed"]:
                print(f"        {check['name']}: {check['detail']}")
        all_passed = all_passed and quality["passed"]
    return all_passed


def main() -> None:
    """Run the evals and set the exit status."""
    sys.exit(0 if asyncio.run(run_evals()) else 1)


if __name__ == "__main__":
    main()
