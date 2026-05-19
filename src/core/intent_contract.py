"""
intent_contract.py
==================
Canonical intent layer used across planners.

Goal:
- avoid brittle single-query hardcoding
- keep a stable contract for complex query decomposition
"""

from __future__ import annotations

import re
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


def is_client_count_query(user_query: str) -> bool:
    """How many clients (not a ranking or name lookup)."""
    q = user_query.lower()
    if "client" not in q:
        return False
    if any(m in q for m in ("combien", "nombre", "denombre", "dénombre", "effectif")):
        return True
    if "total" in q and "client" in q:
        return True
    return False


def _has_superlative_marker(q: str) -> bool:
    return bool(
        re.search(
            r"\b(plus|moins|meilleur|meilleurs|top|principal|premier|premiers|max|maximum)\b",
            q,
        )
    )


def is_client_sales_ranking_query(user_query: str) -> bool:
    """Best / top client by purchase volume or revenue (not a named client lookup)."""
    if is_client_count_query(user_query):
        return False
    q = user_query.lower()
    if "client" not in q:
        return False
    purchase_terms = ("achat", "achete", "achète", "achats", "ca", "chiffre", "affaire", "volume", "vente", "commande")
    if re.search(r"plus\s+d['\u2019]?\s*achat", q):
        return True
    if any(
        phrase in q
        for phrase in (
            "meilleur client",
            "top client",
            "client qui achete",
            "client qui achète",
            "client qui genere",
            "client qui génère",
            "plus d'achat",
            "plus d achat",
            "plus gros chiffre",
            "volume d'achat",
            "volume d achat",
            "classement client",
        )
    ):
        return True
    if "meilleur" in q and "client" in q:
        return True
    if _has_superlative_marker(q) and any(w in q for w in purchase_terms):
        return True
    if re.search(
        r"\b(client|clients)\b.*\b(qui|que)\b.*\b(achete|achète|achetent|genere|génère|genere|commande)\b",
        q,
    ) and _has_superlative_marker(q):
        return True
    if ("qui" in q or "quel" in q) and "client" in q and _has_superlative_marker(q):
        return True
    return False


def is_mdx_exploration_query(user_query: str) -> bool:
    """User explicitly wants MDX/SQL generation or cube OLAP exploration (Phase 4)."""
    q = user_query.lower()
    if any(k in q for k in ("mdx", "olap", "cube")):
        return True
    if "requête" in q or "requete" in q:
        if any(k in q for k in ("mdx", "sql", "olap", "cube")):
            return True
    if any(
        phrase in q
        for phrase in (
            "génère le mdx",
            "genere le mdx",
            "génère le sql",
            "genere le sql",
            "montre le mdx",
            "montre le sql",
            "affiche le mdx",
            "affiche le sql",
        )
    ):
        return True
    return False


def is_dimensional_breakdown_query(user_query: str) -> bool:
    """CA / sales sliced by a dimension (par ville, par client, …), not a master-data lookup."""
    if is_mdx_exploration_query(user_query):
        return False
    if is_client_count_query(user_query) or is_client_sales_ranking_query(user_query):
        return False
    q = user_query.lower()
    if not re.search(r"\bpar\s+[a-zàâäéèêëïîôùûçñ0-9_-]+", q):
        return False
    measure_terms = (
        "chiffre",
        "affaire",
        " ca ",
        "ca ",
        " ca.",
        "vente",
        "ventes",
        "revenue",
        "montant",
        "facturation",
        "recette",
        "quantite",
        "quantité",
        "quantites",
        "quantités",
        "volume",
    )
    padded = f" {q} "
    if not any(t in padded or t.strip() in q for t in measure_terms):
        return False
    if "par mois" in q or "par jour" in q or "par semaine" in q:
        return True
    if "par ville" in q or "par villes" in q:
        return True
    if "par client" in q or "par clients" in q:
        return True
    if "par region" in q or "par région" in q or "par regions" in q:
        return True
    if "par article" in q or "par produit" in q:
        return True
    return bool(re.search(r"\bpar\s+(ville|villes|client|clients|region|région|article|produit)\b", q))


def breakdown_group_by_from_query(user_query: str) -> str:
    """Map natural language to indicateurs groupBy key (sqlite_backend)."""
    q = user_query.lower()
    if "par mois" in q or "mensuel" in q or "monthly" in q:
        return "month"
    if "par jour" in q or "journalier" in q or "daily" in q:
        return "day"
    if "par ville" in q or "par villes" in q:
        return "ville"
    if "par client" in q or "par clients" in q:
        return "client"
    if "par region" in q or "par région" in q or "par regions" in q:
        return "region"
    if "par article" in q or "par produit" in q:
        return "article"
    m = re.search(r"\bpar\s+([a-zàâäéèêëïîôùûçñ]+)", q)
    if m:
        token = m.group(1)
        aliases = {
            "ville": "ville",
            "villes": "ville",
            "client": "client",
            "clients": "client",
            "region": "region",
            "région": "region",
            "article": "article",
            "produit": "article",
            "mois": "month",
            "jour": "day",
        }
        return aliases.get(token, token)
    return "month"


def breakdown_metric_from_query(user_query: str) -> str:
    q = user_query.lower()
    if any(w in q for w in ("quantité", "quantite", "volume", "unité", "unite", "units")):
        return "quantity"
    return "sales"


def client_ranking_sort_metric(user_query: str) -> str:
    q = user_query.lower()
    if any(w in q for w in ("chiffre", "affaire", "ca", "revenue", "montant", "euro", "€")):
        return "ca"
    return "quantite"


def extract_ca_threshold_from_query(user_query: str) -> float | None:
    """Parse a minimum CA threshold from phrases like « supérieur à 60 573,8 »."""
    q = user_query.lower()
    if not any(w in q for w in ("chiffre", "affaire", " ca", "revenue", "montant")):
        return None
    if not re.search(
        r"\b(superieur|supérieur|supérieur|>|au[\s-]?dessus|depass\w*|exced\w*|plus\s+de)\b",
        q,
    ):
        return None
    m = re.search(
        r"(?:superieur|supérieur|>|au[\s-]?dessus|depass\w*|exced\w*|plus\s+de)\s*(?:a|à|de)?\s*([\d][\d\s.,]*)",
        q,
    )
    if not m:
        return None
    num_str = m.group(1).strip().replace("\u202f", " ").replace(" ", "").replace(",", ".")
    try:
        return float(num_str)
    except ValueError:
        return None


def is_client_ca_threshold_query(user_query: str) -> bool:
    """List/filter clients whose revenue exceeds a numeric threshold."""
    if extract_ca_threshold_from_query(user_query) is None:
        return False
    q = user_query.lower()
    if "client" not in q:
        return False
    list_markers = (
        "liste",
        "list",
        "donner",
        "donne",
        "donnez",
        "afficher",
        "montre",
        "montrez",
        "quels clients",
        "quel client",
    )
    if any(m in q for m in list_markers):
        return True
    return "qui ont" in q or "ayant" in q


def wants_tabular_output(user_query: str) -> bool:
    """User explicitly asked for a table layout (FR/EN)."""
    q = user_query.lower()
    patterns = (
        "tableau",
        "en table",
        "sous forme de table",
        "format table",
        "tabulaire",
        "in table",
        "as a table",
        "as table",
        "table format",
        "show table",
        "afficher en tableau",
        "presente en tableau",
        "présente en tableau",
        "sous forme tabulaire",
    )
    return any(p in q for p in patterns)


def wants_chart_output(user_query: str) -> bool:
    """User explicitly asked for a chart (overrides table when both absent)."""
    q = user_query.lower()
    patterns = (
        "graphique",
        "chart",
        "courbe",
        "diagramme",
        "histogramme",
        "camembert",
        "secteur",
        "barres",
        "en graph",
    )
    return any(p in q for p in patterns)


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
        "par ville",
        "par villes",
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
    wants_ranking = bool(
        re.search(
            r"\b(top|ranking|classement|rank|best|most|plus|moins|meilleur|meilleurs|principal|premier|premiers)\b",
            q,
        )
    )
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

    if is_client_sales_ranking_query(user_query):
        return IntentDecision("client_sales_ranking", "high", "classement_clients", False, "")
    if is_mdx_exploration_query(user_query):
        return IntentDecision("mdx_generation", "high", "consulter_indicateurs_analytiques", False, "")
    if is_dimensional_breakdown_query(user_query):
        return IntentDecision("dimensional_breakdown", "high", "consulter_indicateurs_analytiques", False, "")
    if d.wants_forecast:
        return IntentDecision("forecasting", "high", "consulter_indicateurs_analytiques", False, "")
    if d.wants_mdx:
        return IntentDecision("mdx_generation", "high", "consulter_indicateurs_analytiques", False, "")
    if d.wants_ranking and (
        "sell" in q
        or "vendu" in q
        or "vente" in q
        or "achat" in q
        or "achete" in q
        or "achète" in q
        or "achats" in q
    ):
        if "client" in q and ("produit" not in q and "article" not in q):
            return IntentDecision("client_sales_ranking", "high", "classement_clients", False, "")
        return IntentDecision("sales_ranking", "high", "classement_ventes", False, "")
    if d.wants_ranking and d.wants_stock:
        return IntentDecision("stock_ranking", "high", "consulter_stocks", False, "")
    if d.wants_time_series or d.wants_kpi or (
        d.wants_aggregate_exploration
        and not d.wants_stock
        and not d.wants_ranking
        and not is_client_count_query(user_query)
        and not is_client_sales_ranking_query(user_query)
        and not is_dimensional_breakdown_query(user_query)
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
