"""
Optional LangGraph pipeline for Phase 3.

This keeps the existing deterministic implementation untouched and adds
an alternative graph-based execution path for production hardening.
"""

from typing import Any, Dict, Optional, TypedDict

from phase3_agent import aggregate, format_final
from phase3_orchestrator import execute_plan
from phase3_planner import plan


class GraphState(TypedDict, total=False):
    user_query: str
    use_mock_planner: bool
    mock_responses: Optional[dict]
    plan: list
    execution_result: dict
    aggregated: dict
    final_answer: str


def _node_plan(state: GraphState) -> Dict[str, Any]:
    execution_plan = plan(
        state["user_query"],
        use_mock=state.get("use_mock_planner", True),
    )
    return {"plan": execution_plan}


def _node_execute(state: GraphState) -> Dict[str, Any]:
    result = execute_plan(
        state["plan"],
        mock_responses=state.get("mock_responses"),
    )
    return {"execution_result": result}


def _node_aggregate(state: GraphState) -> Dict[str, Any]:
    aggregated = aggregate(state["execution_result"])
    return {"aggregated": aggregated}


def _node_format(state: GraphState) -> Dict[str, Any]:
    final_answer = format_final(state["aggregated"])
    return {"final_answer": final_answer}


def build_phase3_graph():
    """
    Build and compile a LangGraph state machine.
    Raises a helpful error if langgraph is not installed.
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception as exc:
        raise ImportError(
            "LangGraph is not installed. Install with: pip install langgraph"
        ) from exc

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
) -> str:
    """
    Run Phase 3 through LangGraph.
    """
    app = build_phase3_graph()
    result = app.invoke(
        {
            "user_query": user_query,
            "use_mock_planner": use_mock_planner,
            "mock_responses": mock_responses,
        }
    )
    return result.get("final_answer", "")

