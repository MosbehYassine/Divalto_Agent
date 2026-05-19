"""
semantic_router.py
==================
Metadata-driven action/measure routing based on:
- available WS actions from ws_schemas.json
- semantic catalog terms (intent + measures)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.divalto_agent import WS_SCHEMAS
from core.intent_contract import (
    client_ranking_sort_metric,
    is_client_sales_ranking_query,
    is_dimensional_breakdown_query,
)
from phase4.prefunctions import normalize_text


@dataclass(frozen=True)
class ActionScore:
    action: str
    tool_name: str
    domain: str
    score: int
    matched_terms: tuple[str, ...]


def _load_semantic_catalog() -> dict[str, Any]:
    path = Path(__file__).resolve().parent.parent / "config" / "semantic_catalog.json"
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("semantic_catalog.json must contain a top-level object.")
    return data


SEMANTIC_CATALOG = _load_semantic_catalog()


def get_available_actions() -> set[str]:
    return set(WS_SCHEMAS.keys())


def get_action_metadata(action: str) -> dict[str, Any]:
    action_meta = SEMANTIC_CATALOG.get("actions", {}).get(action, {})
    tool_name = action_meta.get("tool_name", action)
    domain = action_meta.get("domain", "generic")
    intent_terms = list(action_meta.get("intent_terms", []))
    measure_terms = list(action_meta.get("measure_terms", []))
    return {
        "tool_name": tool_name,
        "domain": domain,
        "intent_terms": intent_terms,
        "measure_terms": measure_terms,
    }


def score_actions(user_query: str, available_actions: set[str] | None = None) -> dict[str, ActionScore]:
    normalized = normalize_text(user_query)
    available = available_actions or get_available_actions()
    scores: dict[str, ActionScore] = {}
    for action in sorted(available):
        meta = get_action_metadata(action)
        terms = meta["intent_terms"] + meta["measure_terms"]
        score = 0
        matched: list[str] = []
        for term in terms:
            if term and term in normalized:
                score += 2 if term in meta["intent_terms"] else 1
                matched.append(term)
        # Light lexical boost when action identifier itself appears in text.
        action_tokens = [tok for tok in action.split("_") if len(tok) >= 4]
        for tok in action_tokens:
            if tok in normalized:
                score += 1
                matched.append(tok)
        scores[action] = ActionScore(
            action=action,
            tool_name=meta["tool_name"],
            domain=meta["domain"],
            score=score,
            matched_terms=tuple(dict.fromkeys(matched)),
        )
    return scores


def select_best_action(user_query: str, available_actions: set[str] | None = None) -> tuple[str | None, dict[str, Any]]:
    scores = score_actions(user_query, available_actions=available_actions)
    if not scores:
        return None, {
            "selected_action": None,
            "selected_tool": None,
            "score": 0,
            "second_score": 0,
            "score_margin": 0,
            "matched_terms": [],
            "top_candidates": [],
            "confidence": "low",
        }
    ranked = sorted(scores.values(), key=lambda s: s.score, reverse=True)
    best = ranked[0]
    second = ranked[1] if len(ranked) > 1 else ranked[0]
    confidence = "high" if best.score >= 6 else "medium" if best.score >= 2 else "low"
    diagnostics = {
        "selected_action": best.action,
        "selected_tool": best.tool_name,
        "selected_domain": best.domain,
        "score": best.score,
        "second_score": second.score,
        "score_margin": best.score - second.score,
        "matched_terms": list(best.matched_terms),
        "top_candidates": [
            {
                "action": s.action,
                "tool": s.tool_name,
                "domain": s.domain,
                "score": s.score,
                "matched_terms": list(s.matched_terms),
            }
            for s in ranked[:3]
        ],
        "confidence": confidence,
    }
    selected = best.action if best.score > 0 else None
    return selected, diagnostics


def resolve_measure(user_query: str, available_actions: set[str] | None = None) -> dict[str, Any]:
    normalized = normalize_text(user_query)
    available = available_actions or get_available_actions()
    if is_client_sales_ranking_query(user_query) and "classement_clients" in available:
        metric = client_ranking_sort_metric(user_query)
        return {"measure": metric, "recommended_action": "classement_clients"}
    if is_dimensional_breakdown_query(user_query) and "consulter_indicateurs_analytiques" in available:
        from core.intent_contract import breakdown_metric_from_query

        return {
            "measure": breakdown_metric_from_query(user_query),
            "recommended_action": "consulter_indicateurs_analytiques",
        }
    preferences = SEMANTIC_CATALOG.get("measure_preferences", [])
    for pref in preferences:
        terms = pref.get("terms", [])
        if any(term in normalized for term in terms):
            for action in pref.get("preferred_actions", []):
                if action in available:
                    return {
                        "measure": pref.get("measure", "generic"),
                        "recommended_action": action,
                    }
    # Fallback: pick highest score action if any
    action, _ = select_best_action(user_query, available_actions=available)
    if action is None and available:
        action = sorted(available)[0]
    return {"measure": "generic", "recommended_action": action}

