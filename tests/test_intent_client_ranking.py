import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parents[1] / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from core.intent_contract import client_ranking_sort_metric, infer_intent, is_client_sales_ranking_query
from phase3.planner import mock_plan, plan


def test_client_ranking_intent_detected():
    q = "Quel est le client qui génère le plus gros chiffre d'affaires"
    assert is_client_sales_ranking_query(q)
    assert infer_intent(q).intent == "client_sales_ranking"
    assert client_ranking_sort_metric(q) == "ca"


def test_client_ranking_mock_plan():
    q = "Qui est le meilleur client en termes de volume d'achat ?"
    steps = mock_plan(q)
    assert len(steps) == 1
    assert steps[0]["action"] == "classement_clients"
    assert steps[0].get("sortBy") == "quantite"


def test_client_ranking_end_to_end_mock_db():
    q = "Quel client a effectué le plus d'achats"
    steps = plan(q, use_mock=True)
    assert steps[0]["action"] == "classement_clients"
    from phase3.agent import run_phase3

    answer = run_phase3(q, use_mock_planner=True)
    assert "client" in answer.lower()
    assert "aucun client ne correspond" not in answer.lower()
    assert "total des ventes" not in answer.lower()


def test_user_reported_ranking_queries():
    """Regression: natural French variants from chat UI."""
    from phase3.agent import run_phase3
    from phase4.prefunctions import extract_lookup_hint

    cases = [
        (
            "Quel client a effectué le plus d'achats",
            "quantite",
            ("achète le plus", "volume"),
        ),
        (
            "Quel est le client qui génère le plus gros chiffre d'affaires ?",
            "ca",
            ("chiffre d'affaires", "CA"),
        ),
        (
            "Qui est le client qui achète le plus",
            "quantite",
            ("achète le plus", "volume"),
        ),
    ]
    for q, sort_by, answer_fragments in cases:
        assert is_client_sales_ranking_query(q), q
        assert extract_lookup_hint(q) == "", q
        steps = plan(q, use_mock=True)
        assert steps[0]["action"] == "classement_clients", q
        assert steps[0].get("sortBy") == sort_by, q
        answer = run_phase3(q, use_mock_planner=True)
        assert "aucun client ne correspond" not in answer.lower(), q
        assert "total des ventes" not in answer.lower(), q
        assert "correspondent partiellement" not in answer.lower(), q
        assert any(frag.lower() in answer.lower() for frag in answer_fragments), (q, answer)
