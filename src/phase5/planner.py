"""
phase5_planner.py
=================
Phase 5 — analytic multi-call planning.

Builds ordered webservice steps for rankings, totals, comparisons, and
short analytic series aligned with SQLite / ERP payloads.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re

from core.intent_contract import decompose_query, infer_intent, is_client_sales_ranking_query
from llm.ollama_client import call_ollama_json_plan
from phase5.dates import infer_date_bounds_from_question, paired_prior_window
from core.prompt_templates import load_prompt_template
from llm.rag_retriever import retrieve_context
from routing.semantic_router import get_available_actions, resolve_measure
from core.settings import LLM_PLAN_TIMEOUT_SECONDS as _DEFAULT_LLM_PLAN_TIMEOUT


def _effective_llm_plan_timeout() -> float:
    floor_s = 0.05
    raw = os.getenv("DIVALTO_LLM_PLAN_TIMEOUT_SECONDS", "").strip()
    if raw:
        try:
            return max(floor_s, min(float(raw), 120.0))
        except ValueError:
            pass
    return max(floor_s, min(float(_DEFAULT_LLM_PLAN_TIMEOUT), 120.0))


def _extract_customer_hint(user_query: str) -> str:
    m_cli = re.search(r"\bCLI-\d+\b", user_query, flags=re.IGNORECASE)
    if m_cli:
        return m_cli.group(0).upper()
    return ""


def _extract_top_limit(user_query: str) -> int:
    """
    Typical patterns: Top 5, top5, les 3 meilleurs articles...
    """
    t = user_query.lower()
    m = re.search(r"\btop\s*(\d+)\b", t)
    if m:
        return max(1, min(50, int(m.group(1))))
    m_digit = re.search(r"\b(\d+)\s+(meilleurs?|premiers?)\s+articles?\b", t)
    if m_digit:
        return max(1, min(50, int(m_digit.group(1))))
    if "plus vendu" in t or "meilleur produit" in t:
        return 1
    if any(k in t for k in ("classement", "rang")):
        return 5
    if "top" in t:
        return 5
    return 5


def _wants_sales_total(user_query: str) -> bool:
    q = user_query.lower()
    needles = ("ca global", "total des ventes", "ca total", "montant global", "chiffre d'affaires total")
    if any(k in q for k in needles):
        return True
    return ("total" in q and "ca" in q) or ("avec" in q and "ca total" in q)


def _analytics_series_query(user_query: str) -> bool:
    q = user_query.lower()
    keys = ("par mois", "mensuel", "série temporelle", "évolution mensuelle", "evolution mensuelle")
    keys2 = ("courbe", "graphique minimal", "tendance mensuelle")
    return any(k in q for k in keys) or any(k in q for k in keys2)


def _comparison_query(user_query: str) -> bool:
    q = user_query.lower()
    if "compare" in q or "versus" in q or "vs" in q:
        return True
    return "hausse" in q or "baisse" in q or "mois par mois" in q


def plan_phase5(user_query: str, use_mock: bool = True) -> list[dict]:
    """
    Produce a multi-step analytic plan compatible with Phase 3 orchestrator.
    """
    if use_mock:
        result = phase5_mock_plan(user_query)
    else:
        plan_timeout = _effective_llm_plan_timeout()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(llm_plan_phase5, user_query)
                result = fut.result(timeout=plan_timeout)
        except TimeoutError:
            print(
                f"[Phase5 Planner] LLM plan exceeded {plan_timeout}s, fallback to mock: {user_query!r}",
            )
            result = phase5_mock_plan(user_query)
        except Exception as exc:  # noqa: BLE001
            print(f"[Phase5 Planner] Real planner failed, fallback to mock: {exc}")
            result = phase5_mock_plan(user_query)

    print(f"[Phase5 Planner] Query: '{user_query}'")
    print(f"[Phase5 Planner] Plan: {json.dumps(result, ensure_ascii=False)}")
    return result


def phase5_mock_plan(user_query: str) -> list[dict]:
    # Top-client questions belong to Phase 3 classement_clients, not global sales totals.
    if is_client_sales_ranking_query(user_query):
        return []

    q = user_query.lower()
    decomposition = decompose_query(user_query)
    intent = infer_intent(user_query)
    available = get_available_actions()
    start_d, end_d = infer_date_bounds_from_question(user_query)
    customer = _extract_customer_hint(user_query)
    cust_fields: dict[str, str] = {"customer": customer} if customer else {}
    measure_info = resolve_measure(user_query, available_actions=available)
    recommended_action = measure_info.get("recommended_action")

    # Analytic buckets from indicateurs WS (fallback to best available aggregate endpoint)
    if _analytics_series_query(user_query) or decomposition.wants_time_series or intent.intent == "kpi_analysis":
        group_by = "month" if ("mois" in q or "mensuel" in q or "month" in q or "monthly" in q) else "day"
        metric_value = measure_info.get("measure", "sales")
        if metric_value == "generic":
            metric_value = "sales"
        if "consulter_indicateurs_analytiques" not in available:
            fallback_action = recommended_action or ("consulter_ventes" if "consulter_ventes" in available else None)
            if fallback_action:
                return [
                    {
                        "step": 0,
                        "action": fallback_action,
                        "startDate": start_d,
                        "endDate": end_d,
                        **cust_fields,
                    }
                ]
        return [
            {
                "step": 0,
                "action": "consulter_indicateurs_analytiques",
                "metric": "quantity" if "quantité" in q or "quantite" in q else metric_value,
                "startDate": start_d,
                "endDate": end_d,
                "groupBy": group_by,
            }
        ]

    # Comparative totals: contiguous prior window aligned on user window length
    if (_comparison_query(user_query) or decomposition.wants_comparison) and not _analytics_series_query(user_query):
        compare_action = (
            recommended_action
            if recommended_action in {"consulter_ventes", "consulter_facturation"}
            else ("consulter_ventes" if "consulter_ventes" in available else "consulter_facturation")
        )
        if compare_action not in available:
            compare_action = None
        if compare_action is None:
            return []
        if start_d != "19000101" and end_d != "99991231":
            prev_start, prev_end = paired_prior_window(start_d, end_d)
            if prev_start and prev_end:
                return [
                    {"step": 0, "action": compare_action, "startDate": start_d, "endDate": end_d, **cust_fields},
                    {"step": 1, "action": compare_action, "startDate": prev_start, "endDate": prev_end, **cust_fields},
                ]
        return [
            {
                "step": 0,
                "action": compare_action,
                "startDate": "20240101",
                "endDate": "20240131",
                **cust_fields,
            },
            {
                "step": 1,
                "action": compare_action,
                "startDate": "20231201",
                "endDate": "20231231",
                **cust_fields,
            },
        ]

    lim = _extract_top_limit(user_query)

    ranking_action = "classement_ventes" if "classement_ventes" in available else recommended_action
    if ranking_action is None:
        return []
    cls_step: dict = {"step": 0, "action": ranking_action, "startDate": start_d, "endDate": end_d, **cust_fields}
    if "classement_ventes" in available:
        cls_step["limit"] = lim

    # Top seller wants live stock drill-down
    wants_stock = "stock" in q or "dispo" in q or "disponible" in q or "disponibilité" in q
    if wants_stock and "interroger_stock" in available and ranking_action == "classement_ventes":
        merged = [{**cls_step, "limit": max(1, min(lim, 1))}]
        merged.append(
            {
                "step": 1,
                "action": "interroger_stock",
                "reference": "{{step_0.leaderReference}}",
                "warehouse": "*",
            }
        )
        return merged

    steps: list[dict] = [cls_step]

    if _wants_sales_total(user_query):
        total_action = (
            "consulter_ventes"
            if "consulter_ventes" in available
            else "consulter_facturation" if "consulter_facturation" in available else None
        )
        if total_action:
            step: dict = {
                "step": len(steps),
                "action": total_action,
                "startDate": start_d,
                "endDate": end_d,
                **cust_fields,
            }
            steps.append(step)

    return steps


def llm_plan_phase5(user_query: str) -> list[dict]:
    actions = sorted(get_available_actions())
    system_prompt = load_prompt_template("phase5_system").format(actions=", ".join(actions))
    rag = retrieve_context(user_query)
    if rag.get("context"):
        system_prompt += "\n\n" + load_prompt_template("rag_suffix").format(context=rag["context"])
    plan_steps = call_ollama_json_plan(user_query=user_query, system_prompt=system_prompt)
    normalized: list[dict] = []
    for i, step in enumerate(plan_steps):
        copy = dict(step)
        copy["step"] = int(copy.get("step", i))
        normalized.append(copy)
    return normalized
