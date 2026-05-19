import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parents[1] / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from analytics.orchestrator import run_semantic_data_analytics, _wants_sales_by_article
from app.server import _infer_mode_from_query
from core.intent_contract import is_dimensional_breakdown_query, is_mdx_exploration_query


def test_mdx_query_routes_phase4_not_breakdown():
    q = (
        "Requête MDX sur le cube OLAP : génère le MDX et le SQL pour la somme des "
        "quantités vendues (table ventes) regroupées par article, avec aperçu des données."
    )
    assert is_mdx_exploration_query(q)
    assert not is_dimensional_breakdown_query(q)
    assert _infer_mode_from_query(q) == "phase4"
    assert _wants_sales_by_article(q)


def test_sales_by_article_analytic_includes_mdx_sql():
    q = "Analyse MDX cube : quantités vendues par article — montre le MDX, le SQL et les résultats."
    result = run_semantic_data_analytics(q)
    assert result.get("ok"), result.get("error")
    answer = result.get("answer") or ""
    assert "```mdx" in answer
    assert "```sql" in answer
    assert "SELECT" in answer.upper()
    assert "article" in answer.lower()
    assert "correspondent partiellement" not in answer.lower()
