"""
LangGraph smoke test.

If langgraph is not installed on the machine, this test exits cleanly
with a SKIP message instead of failing the whole suite.
"""

import os
import sys


CURRENT_DIR = os.path.dirname(__file__)
SRC_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from langgraph_agent import run_phase3_langgraph  # noqa: E402


def main() -> int:
    try:
        answer = run_phase3_langgraph(
            "Quel est le stock de l'article ALB0001 ?",
            use_mock_planner=True,
            mock_responses={
                "step_0": {
                    "reference": "ALB0001",
                    "warehouse": "*",
                    "quantity": 42,
                }
            },
        )
        if "42" not in answer:
            print(f"FAIL: unexpected answer: {answer}")
            return 1
        print("PASS: LangGraph pipeline returned expected stock answer.")
        return 0
    except ImportError as exc:
        print(f"SKIP: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

