import os
import sys

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from phase3.orchestrator import execute_plan, resolve_references  # noqa: E402


def test_resolve_leader_reference():
    step = {
        "step": 1,
        "action": "interroger_stock",
        "reference": "{{step_0.leaderReference}}",
        "warehouse": "*",
    }
    memory = {"step_0": {"leaderReference": "ART-9", "quantite": 1}}
    resolved = resolve_references(step, memory)
    assert resolved["reference"] == "ART-9"


def test_execute_plan_mock_chain():
    plan = [
        {"step": 0, "action": "article_plus_vendu"},
        {
            "step": 1,
            "action": "interroger_stock",
            "reference": "{{step_0.reference}}",
            "warehouse": "*",
        },
    ]
    mocks = {
        "step_0": {"reference": "CHAIN-1", "quantite": 5, "ca": "10"},
        "step_1": {"reference": "CHAIN-1", "warehouse": "*", "quantity": 2},
    }
    result = execute_plan(plan, mock_responses=mocks)
    assert result["ok"] is True
    assert result["memory"]["step_1"]["quantity"] == 2
