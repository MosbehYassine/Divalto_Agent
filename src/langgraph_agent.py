"""
Optional LangGraph pipeline for Phase 3.

This keeps the existing deterministic implementation untouched and adds
an alternative graph-based execution path for production hardening.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, TypedDict

from governance.context import build_optional_context_from_env
from governance.models import ExecutionApproval
from governance.pipeline import finalize_agent_audit

from phase3_agent import aggregate, format_final
from phase3_orchestrator import execute_plan
from phase3_planner import plan


class GraphState(TypedDict, total=False):
    user_query: str
    use_mock_planner: bool
    mock_responses: Optional[dict]
    correlation_id: str
    approval_allow_irreversible: bool
    approval_actor: str | None
    plan: list
    execution_result: dict
    aggregated: dict
    final_answer: str


def _node_plan(state: GraphState) -> Dict[str, Any]:
    execution_plan = plan(state["user_query"], use_mock=state.get("use_mock_planner", True))
    return {"plan": execution_plan}


def _node_execute(state: GraphState) -> Dict[str, Any]:
    correlation = state.get("correlation_id") or str(uuid.uuid4())
    approval: ExecutionApproval | None = None
    if state.get("approval_allow_irreversible"):
        approval = ExecutionApproval(
            allow_irreversible=True,
            approved_by=state.get("approval_actor"),
            notes="langgraph-state",
        )
    exec_ctx = build_optional_context_from_env(
        user_query=state["user_query"],
        correlation_id=correlation,
        approval=approval,
    )
    execution_plan = state.get("plan", [])
    result = execute_plan(
        execution_plan,
        mock_responses=state.get("mock_responses"),
        execution_context=exec_ctx,
    )
    return {
        "execution_result": result,
        "correlation_id": getattr(exec_ctx, "correlation_id", correlation),
        "_exec_ctx": exec_ctx,
    }


def _node_aggregate(state: GraphState) -> Dict[str, Any]:
    aggregated = aggregate(state["execution_result"])
    return {"aggregated": aggregated}


def _node_format(state: GraphState) -> Dict[str, Any]:
    final_answer = format_final(state["aggregated"], user_query=state.get("user_query") or "")
    finalize_agent_audit(
        state.get("_exec_ctx"),
        plan=state.get("plan") or [],
        execution_result=state.get("execution_result") or {},
        final_answer=final_answer,
    )
    return {"final_answer": final_answer}


def build_phase3_graph():
    """
    Build and compile a LangGraph state machine.
    Raises a helpful error if langgraph is not installed.
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception as exc:
        raise ImportError("LangGraph is not installed. Install with: pip install langgraph") from exc

    graph = StateGraph(GraphState)
    graph.add_node("plan", _node_plan)
    graph.add_node("execute", _node_execute)
    graph.add_node("aggregate", _node_aggregate)
    graph.add_node("format", _node_format)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "aggregate")
    graph.add_edge("aggregate", "format")
    graph.add_edge("format", END)
    return graph.compile()


def run_phase3_langgraph(
    user_query: str,
    use_mock_planner: bool = True,
    mock_responses: Optional[dict] = None,
    *,
    correlation_id: str | None = None,
    approval: ExecutionApproval | None = None,
) -> str:
    """Run Phase 3 through LangGraph."""
    app = build_phase3_graph()
    correlation_seed = (correlation_id or "").strip() or str(uuid.uuid4())
    result_state = app.invoke(
        {
            "user_query": user_query,
            "use_mock_planner": use_mock_planner,
            "mock_responses": mock_responses,
            "correlation_id": correlation_seed,
            "approval_allow_irreversible": bool(approval.allow_irreversible) if approval else False,
            "approval_actor": approval.approved_by if approval else None,
        }
    )
    return result_state.get("final_answer", "")
