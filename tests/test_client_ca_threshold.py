import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parents[1] / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from core.intent_contract import extract_ca_threshold_from_query, is_client_ca_threshold_query
from phase3.agent import run_phase3
from phase3.planner import apply_client_ca_threshold_plan_override, mock_plan


def test_extract_threshold_with_narrow_space():
    q = "liste des clients CA superieur a 60\u202f573,8"
    assert extract_ca_threshold_from_query(q) == 60573.8
    assert is_client_ca_threshold_query(q)


def test_plan_override_uses_analytics():
    q = "donner moi la liste des client qui ont un chiffre d affaire superieur a 60573.8"
    plan = apply_client_ca_threshold_plan_override(q, [{"action": "consulter_clients"}])
    assert plan[0]["action"] == "consulter_indicateurs_analytiques"
    assert plan[0]["minValue"] == 60573.8
    assert plan[0]["groupBy"] == "client"


def test_mock_plan_end_to_end():
    q = "donner moi la liste des clients avec chiffre d affaire superieur a 60573.8"
    plan = mock_plan(q)
    assert plan[0]["action"] == "consulter_indicateurs_analytiques"
    answer = run_phase3(q, use_mock_planner=True)
    assert "60573" in answer or "60 573" in answer
    assert "|" in answer
