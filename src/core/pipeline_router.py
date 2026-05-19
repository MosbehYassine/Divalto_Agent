"""
pipeline_router.py
==================
Single routing table for chat execution modes (SOLID — SRP for api_server).
"""

from __future__ import annotations

from core.intent_contract import (
    decompose_query,
    infer_intent,
    is_client_sales_ranking_query,
    is_dimensional_breakdown_query,
    is_mdx_exploration_query,
)
from phase3.planner import _is_client_count_query


def resolve_execution_mode(query: str) -> str:
    """
    Map a user utterance to runtime mode: classic | phase4 | phase5 | langgraph.
    Priority order is explicit to avoid routing bugs (e.g. MDX before breakdown).
    """
    normalized = query.lower().strip()
    decomposition = decompose_query(query)

    if is_mdx_exploration_query(query) or decomposition.wants_mdx:
        return "phase4"

    if (
        _is_client_count_query(query)
        or is_client_sales_ranking_query(query)
        or is_dimensional_breakdown_query(query)
    ):
        return "classic"

    phase4_hints = (
        "dataset",
        "csv",
        "excel",
        "export",
        "table",
        "sql",
        "query builder",
        "olap",
        "cube",
        "dimension",
        "hierarchy",
        "measure",
    )
    phase5_hints = ("forecast", "prediction", "predictive", "projection")
    langgraph_hints = ("workflow", "agent graph", "langgraph")

    if any(hint in normalized for hint in phase4_hints):
        return "phase4"
    if decomposition.wants_forecast or any(hint in normalized for hint in phase5_hints):
        return "phase5"

    intent = infer_intent(query)
    if (
        decomposition.wants_time_series
        or decomposition.wants_comparison
        or intent.intent == "kpi_analysis"
    ):
        return "phase5"
    if any(hint in normalized for hint in langgraph_hints):
        return "langgraph"
    return "classic"
