"""
phase5_agent.py
===============
Phase 5 — Raisonnement analytique multi‑appels.

Pipeline:
    Demande métier → plan_phase5 → execute_plan (Phase 3 orchestrateur)
                     → agrégats/calculs → formulation finale (tableaux + viz ASCII)
"""

from __future__ import annotations

import json
import sys
from typing import Any

from governance.context import build_optional_context_from_env
from governance.execution_context import AgentExecutionContext
from governance.models import ExecutionApproval
from governance.pipeline import finalize_agent_audit

from phase3.orchestrator import execute_plan
from phase5.analytics import synthesize_answer
from phase5.planner import plan_phase5


def _safe_stdout(text: str) -> str:
    try:
        text.encode(sys.stdout.encoding or "utf-8")
        return text
    except Exception:  # noqa: BLE001
        return text.encode("ascii", errors="replace").decode("ascii")


def run_phase5(
    user_query: str,
    use_mock_planner: bool = True,
    mock_responses: dict[str, Any] | None = None,
    *,
    correlation_id: str | None = None,
    approval: ExecutionApproval | None = None,
    execution_context: AgentExecutionContext | None = None,
) -> str:
    """
    Execute analytic orchestration and return a synthesized French narrative.
    """
    print("\n" + "=" * 60)
    print("PHASE 5 — ANALYSE MULTI-APPELS")
    print(f"Requête : {user_query}")
    print("=" * 60)

    exec_ctx = execution_context or build_optional_context_from_env(
        user_query=user_query,
        correlation_id=correlation_id,
        approval=approval,
    )

    execution_plan = plan_phase5(user_query, use_mock=use_mock_planner)
    result = execute_plan(execution_plan, mock_responses=mock_responses, execution_context=exec_ctx)

    governance = result.get("governance") or {}
    if governance.get("plan_blocked"):
        answer = (
            "Blocage périmètre analytique — "
            f"{governance.get('message', 'plan invalide.')}"
        )
        finalize_agent_audit(
            exec_ctx,
            plan=execution_plan,
            execution_result=result,
            final_answer=answer,
        )
        print(f"\n[Phase5 Réponse]\n{_safe_stdout(answer)}")
        return answer

    if not result.get("steps"):
        err = result.get("error") or "exécution vide"
        answer = f"Impossible de lancer les appels métier orchestrés ({err})."
        finalize_agent_audit(
            exec_ctx,
            plan=execution_plan,
            execution_result=result,
            final_answer=answer,
        )
        print(f"\n[Phase5 Réponse]\n{_safe_stdout(answer)}")
        return answer

    answer = synthesize_answer(user_query, result)
    finalize_agent_audit(
        exec_ctx,
        plan=execution_plan,
        execution_result=result,
        final_answer=answer,
    )

    print(f"\n[Phase5 Réponse]\n{_safe_stdout(answer)}")
    return answer


def run_phase5_structured(
    user_query: str,
    use_mock_planner: bool = True,
    mock_responses: dict[str, Any] | None = None,
    *,
    correlation_id: str | None = None,
    approval: ExecutionApproval | None = None,
    execution_context: AgentExecutionContext | None = None,
) -> dict[str, Any]:
    """
    Debugging helper returning plan, raw execution payloads, et réponse lisible.
    """
    exec_ctx = execution_context or build_optional_context_from_env(
        user_query=user_query,
        correlation_id=correlation_id,
        approval=approval,
    )

    execution_plan = plan_phase5(user_query, use_mock=use_mock_planner)
    exec_result = execute_plan(
        execution_plan,
        mock_responses=mock_responses,
        execution_context=exec_ctx,
    )
    readable = synthesize_answer(user_query, exec_result)
    finalize_agent_audit(
        exec_ctx,
        plan=execution_plan,
        execution_result=exec_result,
        final_answer=readable,
    )
    serializable_plan = json.loads(json.dumps(execution_plan))
    serialized_steps = json.loads(json.dumps(exec_result.get("steps", [])))
    return {
        "plan": serializable_plan,
        "execution": {
            "ok": exec_result.get("ok"),
            "errors": exec_result.get("errors", []),
            "steps": serialized_steps,
            "governance": exec_result.get("governance", {}),
        },
        "answer": readable,
    }


if __name__ == "__main__":
    demo_query = "Top 3 articles sur les 10 derniers jours avec CA total."
    mocks = {
        "step_0": {
            "items": [
                {"rank": 1, "reference": "DEMO-X", "quantite": 5, "ca": "50.25"},
                {"rank": 2, "reference": "DEMO-Y", "quantite": 3, "ca": "30.80"},
                {"rank": 3, "reference": "DEMO-Z", "quantite": 1, "ca": "10.00"},
            ],
            "leaderReference": "DEMO-X",
        },
        "step_1": {"totalVentes": 91.05},
    }
    print(json.dumps(run_phase5_structured(demo_query, mock_responses=mocks), ensure_ascii=False, indent=2))
