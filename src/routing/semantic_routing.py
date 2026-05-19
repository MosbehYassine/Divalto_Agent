"""
semantic_routing.py
===================
Decide when to attach catalog-driven semantic analytics to the classic agent path.
Uses decomposition + lightweight lexical cues — no fixed table or measure names.
"""

from __future__ import annotations

import os

from core.intent_contract import decompose_query, infer_intent
from core.intent_contract import (
    is_client_count_query,
    is_client_sales_ranking_query,
    is_dimensional_breakdown_query,
)


def _runtime_semantic_in_classic_enabled() -> bool:
    return (os.getenv("DIVALTO_SEMANTIC_ANALYTICS_IN_CLASSIC") or "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _runtime_semantic_min_query_len() -> int:
    try:
        return max(4, int(os.getenv("DIVALTO_SEMANTIC_ANALYTICS_MIN_QUERY_LEN", "10")))
    except ValueError:
        return 10


def _looks_like_chitchat(user_query: str) -> bool:
    n = user_query.strip().lower()
    if len(n) < 4:
        return True
    starters = (
        "bonjour",
        "salut",
        "hello",
        "hi",
        "hey",
        "merci",
        "thanks",
        "thank you",
        "au revoir",
        "bye",
        "ok",
        "okay",
        "d'accord",
        "dac",
    )
    if any(n.startswith(s) for s in starters) and len(n) < 48:
        return True
    return False


def classic_semantic_analytics_eligible(user_query: str) -> bool:
    """
    True when the classic pipeline may append semantic SQL/MDX analytics for this utterance.
    """
    if not _runtime_semantic_in_classic_enabled():
        return False
    raw = user_query.strip()
    if len(raw) < _runtime_semantic_min_query_len():
        return False
    if _looks_like_chitchat(raw):
        return False
    # Client totals use Phase 3 + consulter_clients (mock-friendly); never pull LLM semantic block.
    if is_client_count_query(raw):
        return False
    if is_client_sales_ranking_query(raw):
        return False
    if is_dimensional_breakdown_query(raw):
        return False

    d = decompose_query(raw)
    intent = infer_intent(raw)

    if d.wants_stock and not any(
        (
            d.wants_ranking,
            d.wants_kpi,
            d.wants_time_series,
            d.wants_comparison,
            d.wants_mdx,
            d.wants_aggregate_exploration,
        )
    ):
        return False

    if any(
        (
            d.wants_ranking,
            d.wants_time_series,
            d.wants_comparison,
            d.wants_kpi,
            d.wants_mdx,
            d.wants_forecast,
            d.wants_aggregate_exploration,
        )
    ):
        return True

    if intent.intent in ("kpi_analysis", "mdx_generation", "forecasting"):
        return True

    return False
