"""
intent_contract.py
==================
Canonical intent layer used across planners.

Goal:
- avoid brittle single-query hardcoding
- keep a stable contract for complex query decomposition
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentDecision:
    intent: str
    confidence: str
    action_hint: str
    requires_clarification: bool
    clarification_message: str


@dataclass(frozen=True)
class QueryDecomposition:
    wants_ranking: bool = False
    wants_stock: bool = False
    wants_time_series: bool = False
    wants_comparison: bool = False
    wants_forecast: bool = False
    wants_mdx: bool = False
    wants_kpi: bool = False
    wants_aggregate_exploration: bool = False


def _wants_aggregate_exploration(q: str) -> bool:
    n = q.lower()
    tokens = (
        "combien",
        "nombre",
        "total",
        "somme",
        "moyenne",
        "average",
        "sum",
        "count",
        "statistique",
        "statistiques",
        "rapport",
        "breakdown",
        "répartition",
        "repartition",
        "group by",
        "groupby",
        "par client",
        "par article",
        "par produit",
        "par mois",
        "par semaine",
        "par jour",
        "par région",
        "par region",
        "données",
        "donnees",
        "dataset",
        "distribution",
        "histogram",
        "effectif",
    )
    return any(t in n for t in tokens)


def decompose_query(user_query: str) -> QueryDecomposition:
    q = user_query.lower()
    wants_ranking = any(k in q for k in ("top", "ranking", "classement", "rank", "best", "most"))
    wants_stock = any(k in q for k in ("stock", "inventory", "dispo", "disponible"))
    wants_time_series = any(k in q for k in ("trend", "tendance", "par mois", "monthly", "time series"))
    wants_comparison = any(k in q for k in ("compare", "versus", "vs", "hausse", "baisse"))
    wants_forecast = any(k in q for k in ("forecast", "prediction", "projection", "predictive"))
    wants_mdx = any(k in q for k in ("mdx", "cube", "olap", "dimension", "hierarchy", "measure"))
    wants_kpi = any(k in q for k in ("kpi", "indicator", "indicateur", "analytics", "analyse", "analysis"))
    wants_aggregate_exploration = _wants_aggregate_exploration(q)
    return QueryDecomposition(
        wants_ranking=wants_ranking,
        wants_stock=wants_stock,
        wants_time_series=wants_time_series,
        wants_comparison=wants_comparison,
        wants_forecast=wants_forecast,
        wants_mdx=wants_mdx,
        wants_kpi=wants_kpi,
        wants_aggregate_exploration=wants_aggregate_exploration,
    )


def infer_intent(user_query: str) -> IntentDecision:
    d = decompose_query(user_query)
    q = user_query.lower()

    if d.wants_forecast:
        return IntentDecision("forecasting", "high", "consulter_indicateurs_analytiques", False, "")
    if d.wants_mdx:
        return IntentDecision("mdx_generation", "high", "consulter_indicateurs_analytiques", False, "")
    if d.wants_ranking and ("sell" in q or "vendu" in q or "vente" in q):
        return IntentDecision("sales_ranking", "high", "classement_ventes", False, "")
    if d.wants_ranking and d.wants_stock:
        return IntentDecision("stock_ranking", "high", "consulter_stocks", False, "")
    if d.wants_time_series or d.wants_kpi or (
        d.wants_aggregate_exploration
        and not d.wants_stock
        and not d.wants_ranking
        and not (
            "client" in q
            and any(w in q for w in ("combien", "nombre", "effectif", "denombre", "dénombre", "total des client"))
        )
    ):
        return IntentDecision("kpi_analysis", "medium", "consulter_indicateurs_analytiques", False, "")
    if d.wants_stock:
        if any(tok in q for tok in ("alb", "ref", "reference", "article ")):
            return IntentDecision("stock_lookup", "high", "interroger_stock", False, "")
        return IntentDecision(
            "stock_lookup",
            "low",
            "interroger_stock",
            True,
            "J'ai besoin d'une référence article (ex: ALB0001) ou d'un objectif clair (top stock, comparaison, tendance).",
        )
    return IntentDecision("generic_business_query", "medium", "", False, "")
