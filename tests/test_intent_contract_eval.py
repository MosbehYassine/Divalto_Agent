import os
import sys

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from intent_contract import infer_intent  # noqa: E402
from phase3_planner import mock_plan  # noqa: E402


def _first_action(query: str) -> str:
    plan = mock_plan(query)
    return str(plan[0]["action"]) if plan else ""


def test_intent_contract_benchmark_queries():
    benchmark = [
        ("what the most selling product ?", "article_plus_vendu"),
        ("donne le top des ventes", "classement_ventes"),
        ("show sales ranking", "classement_ventes"),
        ("stock ALB0001", "interroger_stock"),
        ("which product has highest stock", "consulter_stocks"),
        ("donne le stock max", "consulter_stocks"),
        ("compare sales this month vs last month", "consulter_ventes"),
        ("kpi trend by month", "consulter_indicateurs_analytiques"),
        ("sales analytics by month", "consulter_indicateurs_analytiques"),
    ]
    for query, expected_action in benchmark:
        assert _first_action(query) == expected_action, query


def test_intent_clarification_contract_for_ambiguous_stock():
    decision = infer_intent("stock ?")
    assert decision.intent == "stock_lookup"
    assert decision.requires_clarification is True
    assert "ALB0001" in decision.clarification_message
