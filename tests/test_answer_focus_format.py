"""Formatting focused answers for catalog-style ERP payloads."""

import os
import sys

CURRENT_DIR = os.path.dirname(__file__)
SRC_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from divalto_agent import format_response  # noqa: E402
from phase4_prefunctions import extract_lookup_hint  # noqa: E402
from phase3_planner import apply_client_count_plan_override  # noqa: E402


def test_client_count_plan_overrides_wrong_stock_plan():
    bad_plan = [
        {"step": 0, "action": "interroger_stock", "reference": "UNKNOWN_REFERENCE", "warehouse": "*"}
    ]
    fixed = apply_client_count_plan_override("combien de clients", bad_plan)
    assert len(fixed) == 1
    assert fixed[0]["action"] == "consulter_clients"
    assert fixed[0].get("aggregate") == "count"


def test_extract_lookup_hint_client_phrase():
    hint = extract_lookup_hint("Informations sur le client Dupont Martin")
    assert "dupont" in hint.lower()


def test_format_clients_picks_matching_row():
    payload = {
        "count": 3,
        "clients": [
            {"id": 1, "nom": "AAA Wholesale", "email": "a@x.fr", "ville": "Lille"},
            {"id": 2, "nom": "Martin Dupont", "email": "md@exemple.fr", "ville": "Paris"},
            {"id": 3, "nom": "Zoe Zen", "email": "z@z.fr", "ville": "Lyon"},
        ],
    }
    answer = format_response("consulter_clients", payload, user_query="Que sais-tu du client Martin Dupont ?")
    assert "Martin Dupont" in answer
    assert "md@exemple.fr" in answer
    assert "AAA Wholesale" not in answer


def test_format_clients_count_aggregate():
    answer = format_response(
        "consulter_clients",
        {"aggregate": "count", "totalClients": 120, "count": 120, "clients": []},
        user_query="donner moi le nombre des clients",
    )
    assert "120" in answer
    assert "client" in answer.lower()


def test_format_articles_single_sentence():
    payload = {
        "count": 1,
        "articles": [{"id": 10, "reference": "Clavier mécanique", "prix_unitaire": 89.9}],
    }
    answer = format_response("consulter_articles", payload, user_query="article Clavier mécanique")
    assert "Clavier mécanique" in answer
    assert "89.9" in answer
