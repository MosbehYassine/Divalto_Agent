"""
Unified CLI entrypoint for project execution.
"""

import argparse
import json

from phase3_agent import run_phase3


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Divalto agent unified runner")
    parser.add_argument("--query", required=True, help="User business query")
    parser.add_argument(
        "--mode",
        choices=["classic", "langgraph"],
        default="classic",
        help="Execution mode (classic pipeline or LangGraph pipeline).",
    )
    parser.add_argument(
        "--real-planner",
        action="store_true",
        help="Use non-mock planner (requires real planner endpoint implementation).",
    )
    parser.add_argument(
        "--mock-responses-json",
        default="",
        help="Optional JSON string for mock responses. Example: '{\"step_0\": {\"quantity\": 42}}'",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    mock_responses = None
    if args.mock_responses_json:
        mock_responses = json.loads(args.mock_responses_json)

    use_mock_planner = not args.real_planner

    if args.mode == "langgraph":
        from langgraph_agent import run_phase3_langgraph

        answer = run_phase3_langgraph(
            args.query,
            use_mock_planner=use_mock_planner,
            mock_responses=mock_responses,
        )
    else:
        answer = run_phase3(
            args.query,
            use_mock_planner=use_mock_planner,
            mock_responses=mock_responses,
        )

    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
