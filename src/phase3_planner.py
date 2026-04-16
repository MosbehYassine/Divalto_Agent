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

import json
import re


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

def mock_plan(user_query: str) -> list:
    """
    Rule-based planner for testing.
    Detects intent from keywords and returns a hardcoded plan.
    """
    q = user_query.lower()

    # Pattern 1: top seller + its stock
    if ("plus vendu" in q or "top" in q or "best seller" in q) and \
       ("stock" in q or "reste" in q or "dispo" in q):
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

    # Pattern 2: stock only
    if "stock" in q or "combien" in q or "disponible" in q:
        ref = _extract_ref(user_query)
        return [
            {
                "step":      0,
                "action":    "interroger_stock",
                "reference": ref or "ALB0001",
                "warehouse": "*"
            }
        ]

    # Pattern 3: top seller only
    if "plus vendu" in q or "meilleur" in q or "top" in q:
        return [
            {
                "step":   0,
                "action": "article_plus_vendu"
            }
        ]

    # Pattern 4: sales comparison (this month vs last)
    if ("compar" in q or "évolution" in q or "hausse" in q or
        "baisse" in q or "mois" in q):
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

    # Fallback: single stock query
    return [
        {
            "step":      0,
            "action":    "interroger_stock",
            "reference": _extract_ref(user_query) or "ALB0001",
            "warehouse": "*"
        }
    ]


def _extract_ref(text: str) -> str:
    """Extract article reference pattern like ALB0001 from text."""
    match = re.search(r'\b[A-Z]{2,5}\d{3,6}\b', text)
    return match.group(0) if match else ""


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


def plan(user_query: str, use_mock: bool = True) -> list:
    """
    Public entry point.
    use_mock=True  → rule-based (no LLM needed, for testing)
    use_mock=False → real LLM endpoint (production)
    """
    if use_mock:
        result = mock_plan(user_query)
    else:
        result = llm_plan(user_query)

    print(f"[Planner] Query: '{user_query}'")
    print(f"[Planner] Plan: {json.dumps(result, ensure_ascii=False)}")
    return result
