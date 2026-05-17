"""
phase3_planner.py
=================
Phase 3 — Step 1: The Tool Planner

Responsibility: take a free-form user question and produce
an ordered list of WS calls to make (the "plan").

In production this calls your fine-tuned LLM.
In mock mode it uses rule-based matching so you can test
everything without an LLM endpoint either.
"""

import concurrent.futures
import json
import os
import re

from intent_contract import decompose_query, infer_intent
from ollama_client import call_ollama_json_plan
from phase4_prefunctions import extract_lookup_hint, normalize_text
from prompt_templates import load_prompt_template
from rag_retriever import retrieve_context
from semantic_router import get_available_actions, select_best_action
from settings import LLM_PLAN_TIMEOUT_SECONDS as _DEFAULT_LLM_PLAN_TIMEOUT

# ─────────────────────────────────────────────
# PLAN SCHEMA
#
# A plan is a list of steps. Each step is:
# {
#   "step":   0,
#   "action": "interroger_stock",
#   "ref":    "explicit value OR {{step_N.field}} to resolve later"
#   ... other fields
# }
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# MOCK PLANNER  (no LLM needed)
#
# Maps query patterns → plans.
# Replace mock_plan() with llm_plan() once you
# have a real LLM endpoint.
# ─────────────────────────────────────────────

def _is_client_count_query(user_query: str) -> bool:
    """True when the user asks for how many clients (not a detail lookup)."""
    q = normalize_text(user_query)
    if "client" not in q:
        return False
    if any(m in q for m in ("combien", "nombre", "denombre", "effectif")):
        return True
    if "total" in q:
        return True
    return False


def mock_plan(user_query: str) -> list:
    """
    Rule-based planner for testing.
    Detects intent from keywords and returns a hardcoded plan.
    """
    q = user_query.lower()
    available = get_available_actions()
    decomposition = decompose_query(user_query)
    intent = infer_intent(user_query)

    if "consulter_clients" in available and _is_client_count_query(user_query):
        step: dict = {"step": 0, "action": "consulter_clients", "aggregate": "count"}
        hint = extract_lookup_hint(user_query)
        if hint:
            step["customer"] = hint
        return [step]

    if intent.intent == "sales_ranking" and "classement_ventes" in available and _is_sales_ranking_query(user_query):
        return [{"step": 0, "action": "classement_ventes", "limit": 5, "order": "desc"}]
    if (
        intent.intent == "sales_ranking"
        and "article_plus_vendu" in available
        and not decomposition.wants_stock
    ):
        return [{"step": 0, "action": "article_plus_vendu"}]

    if intent.intent == "stock_ranking" and "consulter_stocks" in available:
        return [{"step": 0, "action": "consulter_stocks", "reference": "", "limit": 1, "order": "desc"}]

    # Pattern 1: top seller + its stock
    if (
        "article_plus_vendu" in available
        and "interroger_stock" in available
        and ("plus vendu" in q or "top" in q or "best seller" in q)
        and ("stock" in q or "reste" in q or "dispo" in q)
    ):
        return [
            {
                "step":   0,
                "action": "article_plus_vendu"
            },
            {
                "step":      1,
                "action":    "interroger_stock",
                "reference": "{{step_0.reference}}",  # inject from step 0
                "warehouse": "*"
            }
        ]

    # Pattern 1b: least sold product
    if "classement_ventes" in available and _is_low_seller_query(user_query):
        return [
            {
                "step": 0,
                "action": "classement_ventes",
                "limit": 1,
                "order": "asc",
            }
        ]

    # Pattern 1bb: explicit sales ranking requests.
    if "classement_ventes" in available and _is_sales_ranking_query(user_query):
        return [
            {
                "step": 0,
                "action": "classement_ventes",
                "limit": 5,
                "order": "desc",
            }
        ]

    # Pattern 1c: stock ranking intent (highest stock product).
    # Route to stock catalog query instead of asking for a fixed reference.
    if (
        "consulter_stocks" in available
        and _is_most_in_stock_query(user_query)
    ):
        return [
            {
                "step": 0,
                "action": "consulter_stocks",
                "reference": "",
                "limit": 1,
                "order": "desc",
            }
        ]

    # Pattern 2: single-article stock — never treat bare « combien » as stock (e.g. « combien de clients »).
    combien_stockish = "combien" in q and (
        "article" in q
        or "produit" in q
        or "référence" in q
        or "reference" in q
        or "stock" in q
        or "dispo" in q
        or "disponible" in q
        or bool(_extract_ref(user_query))
    )
    if (
        "interroger_stock" in available
        and not _is_client_count_query(user_query)
        and ("stock" in q or "disponible" in q or "dispo" in q or combien_stockish)
    ):
        ref = _extract_ref(user_query)
        return [
            {
                "step":      0,
                "action":    "interroger_stock",
                "reference": ref or "UNKNOWN_REFERENCE",
                "warehouse": "*"
            }
        ]

    # Pattern 3: top seller only
    if "article_plus_vendu" in available and _is_top_seller_query(user_query):
        return [
            {
                "step":   0,
                "action": "article_plus_vendu"
            }
        ]

    # Pattern 4: sales comparison (this month vs last)
    if (
        "consulter_ventes" in available
        and ("compar" in q or "évolution" in q or "hausse" in q or "baisse" in q or "mois" in q)
    ):
        return [
            {
                "step":      0,
                "action":    "consulter_ventes",
                "startDate": "20240101",
                "endDate":   "20240131"
            },
            {
                "step":      1,
                "action":    "consulter_ventes",
                "startDate": "20231201",
                "endDate":   "20231231"
            }
        ]

    # Fallback: semantic routing instead of fixed stock hardcoding.
    # This keeps behavior responsive across broader query phrasings.
    if available:
        generic_action, diagnostics = select_best_action(user_query, available_actions=available)
        if not generic_action:
            generic_action = sorted(available)[0]
        step = {"step": 0, "action": generic_action}
        if generic_action == "interroger_stock":
            step["reference"] = _extract_ref(user_query) or "UNKNOWN_REFERENCE"
            step["warehouse"] = "*"
        elif generic_action == "classement_ventes":
            step.setdefault("limit", 5)
            step.setdefault("order", "desc")
        elif generic_action == "consulter_stocks":
            # Generic inventory query returns a sorted list by quantity.
            hint = extract_lookup_hint(user_query)
            step.setdefault("reference", hint)
            step.setdefault("limit", 12 if hint else 20)
            step.setdefault("order", "desc")
        elif generic_action == "consulter_clients":
            hint = extract_lookup_hint(user_query)
            step["customer"] = hint
            step.setdefault("limit", 15 if hint else 12)
        elif generic_action == "consulter_articles":
            hint = extract_lookup_hint(user_query)
            step["reference"] = hint
            step.setdefault("limit", 15 if hint else 12)
        if diagnostics:
            step["routing_confidence"] = diagnostics.get("confidence", "low")
        return [step]
    return []


def _extract_ref(text: str) -> str:
    """Extract article reference pattern like ALB0001 or article label."""
    match = re.search(r'\b[A-Z]{2,5}\d{3,6}\b', text)
    if match:
        return match.group(0)

    # Fallback: capture plain designation in queries like:
    # "stock de l'article Clavier ?"
    label_match = re.search(r"article\s+([A-Za-zÀ-ÿ0-9_-]+)", text, flags=re.IGNORECASE)
    if label_match:
        return label_match.group(1).strip()
    return ""


def _is_low_seller_query(user_query: str) -> bool:
    q = user_query.lower()
    return ("moins vendu" in q) or ("least sold" in q) or ("plus faible vente" in q)


def _is_top_seller_query(user_query: str) -> bool:
    q = user_query.lower()
    if any(k in q for k in ("classement", "ranking", "rank")):
        return False
    if "top des ventes" in q or "top ventes" in q:
        return False
    return (
        ("plus vendu" in q)
        or ("best seller" in q)
        or ("top seller" in q)
        or ("most selling" in q)
        or ("most sold" in q)
        or ("meilleur produit" in q)
        or ("top" in q and ("vente" in q or "sold" in q or "selling" in q))
    )


def _is_sales_ranking_query(user_query: str) -> bool:
    q = user_query.lower()
    return (
        ("ranking" in q)
        or ("rank" in q and "sale" in q)
        or ("classement" in q and ("vente" in q or "sales" in q))
        or ("top sales" in q)
        or ("sales ranking" in q)
        or ("top des ventes" in q)
        or ("top ventes" in q)
    )


def _is_most_in_stock_query(user_query: str) -> bool:
    q = user_query.lower()
    has_stock = ("stock" in q) or ("dispo" in q) or ("disponible" in q)
    has_superlative = (
        ("plus" in q and ("grand" in q or "élevé" in q))
        or "max" in q
        or "maximum" in q
        or "top" in q
        or "highest" in q
        or "most" in q
    )
    return has_stock and has_superlative


def _normalize_plan_for_rank_intent(user_query: str, plan_steps: list[dict]) -> list[dict]:
    """
    Normalize ranking intent so downstream formatting can answer correctly.
    Keeps LLM flexibility while enforcing a stable contract for least-sold queries.
    """
    if not _is_low_seller_query(user_query):
        return plan_steps
    normalized: list[dict] = []
    for i, step in enumerate(plan_steps):
        copy = dict(step)
        copy["step"] = int(copy.get("step", i))
        if copy.get("action") == "classement_ventes":
            copy.setdefault("limit", 1)
            copy["order"] = "asc"
        normalized.append(copy)
    if not normalized:
        return normalized
    # If LLM missed ranking action for a least-sold intent, force a single ranking step.
    has_ranking = any(s.get("action") == "classement_ventes" for s in normalized)
    if not has_ranking:
        return [{"step": 0, "action": "classement_ventes", "limit": 1, "order": "asc"}]
    return normalized


# ─────────────────────────────────────────────
# LLM PLANNER  (production — needs endpoint)
#
# Uncomment and fill in BASE_URL when ready.
# ─────────────────────────────────────────────

# import requests
# LLM_URL = "https://your-llm-endpoint/v1/chat/completions"
#
# SYSTEM_PROMPT = """
# Tu es un planificateur d'outils pour un agent ERP Divalto.
# Tu reçois une question métier en français.
# Tu réponds UNIQUEMENT avec un JSON array de steps, comme ceci:
#
# [
#   {"step": 0, "action": "article_plus_vendu"},
#   {"step": 1, "action": "interroger_stock",
#    "reference": "{{step_0.reference}}", "warehouse": "*"}
# ]
#
# Actions disponibles: interroger_stock, article_plus_vendu,
#                      consulter_ventes, consulter_client,
#                      consulter_facturation, integrer_piece
#
# Utilise {{step_N.field}} pour référencer le résultat d'une étape précédente.
# Ne génère AUCUN texte en dehors du JSON.
# """
#
# def llm_plan(user_query: str) -> list:
#     response = requests.post(LLM_URL, json={
#         "model": "your-finetuned-model",
#         "messages": [
#             {"role": "system", "content": SYSTEM_PROMPT},
#             {"role": "user",   "content": user_query}
#         ]
#     })
#     content = response.json()["choices"][0]["message"]["content"]
#     return json.loads(content)


def llm_plan(user_query: str) -> list:
    """
    Hook for production planners. Wired only when endpoints are configured.
    """
    actions = sorted(get_available_actions())
    system_prompt = load_prompt_template("phase3_system").format(actions=", ".join(actions))
    rag = retrieve_context(user_query)
    if rag.get("context"):
        system_prompt += "\n\n" + load_prompt_template("rag_suffix").format(context=rag["context"])
    plan_steps = call_ollama_json_plan(user_query=user_query, system_prompt=system_prompt)
    # normalize step ids if model omitted them
    normalized = []
    for i, step in enumerate(plan_steps):
        copy = dict(step)
        copy["step"] = int(copy.get("step", i))
        normalized.append(copy)
    return _normalize_plan_for_rank_intent(user_query, normalized)


def apply_client_count_plan_override(user_query: str, plan_steps: list[dict]) -> list[dict]:
    """
    Force consulter_clients + COUNT when the user asks for a client total.
    Overrides LLM/mock mistakes such as interroger_stock on « combien de clients ».
    """
    if not _is_client_count_query(user_query):
        return plan_steps
    if "consulter_clients" not in get_available_actions():
        return plan_steps
    step: dict = {"step": 0, "action": "consulter_clients", "aggregate": "count"}
    hint = extract_lookup_hint(user_query)
    if hint:
        step["customer"] = hint
    return [step]


def enrich_plan_lookup_hints(user_query: str, plan_steps: list[dict]) -> list[dict]:
    """When the model omits filters, derive client/article hints from the question text."""
    if _is_client_count_query(user_query):
        # Count queries use optional filters only; avoid stuffing unrelated hints into customer.
        hint = extract_lookup_hint(user_query)
        if not hint:
            return plan_steps
    else:
        hint = extract_lookup_hint(user_query)
    if not hint:
        return plan_steps
    enriched: list[dict] = []
    for step in plan_steps:
        copy = dict(step)
        act = copy.get("action")
        if act == "consulter_clients" and not str(copy.get("customer") or "").strip():
            copy["customer"] = hint
        elif act == "consulter_articles" and not str(copy.get("reference") or "").strip():
            copy["reference"] = hint
        elif act == "consulter_stocks" and not str(copy.get("reference") or "").strip():
            copy["reference"] = hint
        enriched.append(copy)
    return enriched


def deterministic_llm_bypass_plan(user_query: str) -> list | None:
    """
    Fully rule-based plans that must never wait on Ollama (e.g. client COUNT).
    """
    available = get_available_actions()
    if "consulter_clients" in available and _is_client_count_query(user_query):
        step: dict = {"step": 0, "action": "consulter_clients", "aggregate": "count"}
        hint = extract_lookup_hint(user_query)
        if hint:
            step["customer"] = hint
        return [step]
    return None


def _effective_llm_plan_timeout() -> float:
    """Wall-clock cap for Ollama JSON planner; allow sub-second values for tests and tight SLAs."""
    floor_s = 0.05
    raw = os.getenv("DIVALTO_LLM_PLAN_TIMEOUT_SECONDS", "").strip()
    if raw:
        try:
            return max(floor_s, min(float(raw), 120.0))
        except ValueError:
            pass
    return max(floor_s, min(float(_DEFAULT_LLM_PLAN_TIMEOUT), 120.0))


def plan(user_query: str, use_mock: bool = True) -> list:
    """
    Public entry point.
    use_mock=True  → rule-based (no LLM needed, for testing)
    use_mock=False → real LLM endpoint (production)
    """
    bypass = deterministic_llm_bypass_plan(user_query)
    if bypass is not None:
        result = bypass
    elif use_mock:
        result = mock_plan(user_query)
    else:
        plan_timeout = _effective_llm_plan_timeout()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(llm_plan, user_query)
                result = fut.result(timeout=plan_timeout)
        except TimeoutError:
            print(
                f"[Planner] LLM plan exceeded {plan_timeout}s, fallback to mock: {user_query!r}",
            )
            result = mock_plan(user_query)
        except Exception as exc:  # noqa: BLE001
            # Latency/availability guardrail: keep answering with deterministic fallback.
            print(f"[Planner] Real planner failed, fallback to mock: {exc}")
            result = mock_plan(user_query)

    result = apply_client_count_plan_override(user_query, result)
    result = enrich_plan_lookup_hints(user_query, result)

    print(f"[Planner] Query: '{user_query}'")
    print(f"[Planner] Plan: {json.dumps(result, ensure_ascii=False)}")
    return result
