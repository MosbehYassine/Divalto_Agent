import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parents[1] / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from core.intent_contract import (
    breakdown_group_by_from_query,
    infer_intent,
    is_dimensional_breakdown_query,
)
from phase3.agent import run_phase3
from phase3.planner import plan
from phase4.prefunctions import extract_lookup_hint


def test_ca_par_ville_intent_and_plan():
    q = "Chiffre d'affaires par ville pour les clients"
    assert is_dimensional_breakdown_query(q)
    assert infer_intent(q).intent == "dimensional_breakdown"
    assert breakdown_group_by_from_query(q) == "ville"
    assert extract_lookup_hint(q) == ""
    steps = plan(q, use_mock=True)
    assert steps[0]["action"] == "consulter_indicateurs_analytiques"
    assert steps[0]["groupBy"] == "ville"


def test_ca_par_ville_end_to_end():
    q = "Chiffre d'affaires par ville pour les clients"
    answer = run_phase3(q, use_mock_planner=True)
    assert "par ville" in answer.lower()
    assert "correspondent partiellement" not in answer.lower()
    assert "aucun client ne correspond" not in answer.lower()
    assert "|" in answer
