"""
Unified CLI entrypoint for project execution.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from governance.models import ExecutionApproval
from full_auto_run import (
    _resolve_default_paths,
    ensure_olap_readiness,
    ensure_olap_readiness_async,
)
from settings import (
    AUTO_OLAP_ASYNC_REFRESH,
    AUTO_OLAP_FORCE_REFRESH,
    AUTO_OLAP_PROCESS_SSAS,
    AUTO_OLAP_REFRESH_ENABLED,
    AUTO_OLAP_SSAS_COMMAND,
)

from phase3_agent import run_phase3
from phase4_agent import run_phase4
from phase5_agent import run_phase5


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Divalto agent unified runner")
    parser.add_argument("--query", required=True, help="User business query")
    parser.add_argument(
        "--mode",
        choices=["classic", "langgraph", "phase4", "phase5"],
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
    parser.add_argument(
        "--dataset-output-dir",
        default="",
        help="Optional output directory for Phase 4 dataset artifact export.",
    )
    parser.add_argument(
        "--correlation-id",
        default="",
        help="Optional correlation id propagated to audits / governance telemetry.",
    )
    parser.add_argument(
        "--approve-irreversible",
        action="store_true",
        help="Mark irreversible tooling (integrer_piece, …) as operator-approved.",
    )
    parser.add_argument(
        "--approved-by",
        default="cli-operator",
        help="Label stored next to approvals for audit trails.",
    )
    parser.add_argument(
        "--verbose-logging",
        action="store_true",
        help="Enable INFO logs for planners/orchestrator (stdout).",
    )
    parser.add_argument(
        "--skip-auto-refresh",
        action="store_true",
        help="Skip automatic DW/OLAP refresh check on startup.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.verbose_logging:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
    logger = logging.getLogger("main")

    if not args.skip_auto_refresh:
        defaults = _resolve_default_paths()
        if AUTO_OLAP_ASYNC_REFRESH:
            refresh = ensure_olap_readiness_async(
                python_executable=sys.executable,
                etl_script=defaults["etl_script"],
                source_sqlite=defaults["source_sqlite"],
                olap_output_dir=defaults["olap_output_dir"],
                auto_refresh_enabled=AUTO_OLAP_REFRESH_ENABLED,
                force_refresh=AUTO_OLAP_FORCE_REFRESH,
                process_ssas=AUTO_OLAP_PROCESS_SSAS,
                ssas_command=AUTO_OLAP_SSAS_COMMAND,
            )
        else:
            refresh = ensure_olap_readiness(
                python_executable=sys.executable,
                etl_script=defaults["etl_script"],
                source_sqlite=defaults["source_sqlite"],
                olap_output_dir=defaults["olap_output_dir"],
                auto_refresh_enabled=AUTO_OLAP_REFRESH_ENABLED,
                force_refresh=AUTO_OLAP_FORCE_REFRESH,
                process_ssas=AUTO_OLAP_PROCESS_SSAS,
                ssas_command=AUTO_OLAP_SSAS_COMMAND,
            )
        if not refresh.get("ok", False):
            logger.error("Automatic OLAP refresh failed: %s", refresh)
            return 3
        if args.verbose_logging:
            logger.info("Automatic OLAP readiness check: %s", json.dumps(refresh, ensure_ascii=False))

    mock_responses = None
    if args.mock_responses_json:
        mock_responses = json.loads(args.mock_responses_json)

    use_mock_planner = not args.real_planner

    approval: ExecutionApproval | None = None
    if args.approve_irreversible:
        approval = ExecutionApproval(
            allow_irreversible=True,
            approved_by=args.approved_by,
            notes="cli-flag",
        )
    corr_id = args.correlation_id.strip() or None

    if args.mode == "langgraph":
        from langgraph_agent import run_phase3_langgraph

        answer = run_phase3_langgraph(
            args.query,
            use_mock_planner=use_mock_planner,
            mock_responses=mock_responses,
            correlation_id=corr_id,
            approval=approval,
        )
    elif args.mode == "phase4":
        phase4_result = run_phase4(
            args.query,
            dataset_output_dir=args.dataset_output_dir or None,
        )
        answer = json.dumps(phase4_result, ensure_ascii=False)
    elif args.mode == "phase5":
        answer = run_phase5(
            args.query,
            use_mock_planner=use_mock_planner,
            mock_responses=mock_responses,
            correlation_id=corr_id,
            approval=approval,
        )
    else:
        answer = run_phase3(
            args.query,
            use_mock_planner=use_mock_planner,
            mock_responses=mock_responses,
            correlation_id=corr_id,
            approval=approval,
        )

    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
