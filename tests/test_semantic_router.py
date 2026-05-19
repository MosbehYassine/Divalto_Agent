import os
import sys

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from routing.semantic_router import resolve_measure, select_best_action  # noqa: E402


def test_select_best_action_prefers_facturation_terms():
    action, diagnostics = select_best_action(
        "Montre la facturation du client CLI-001",
        available_actions={"consulter_facturation", "consulter_ventes"},
    )
    assert action == "consulter_facturation"
    assert diagnostics["confidence"] in {"medium", "high"}


def test_select_best_action_returns_none_when_no_signal():
    action, diagnostics = select_best_action(
        "blabla neutre",
        available_actions={"consulter_facturation", "consulter_ventes"},
    )
    assert action is None
    assert diagnostics["confidence"] == "low"


def test_resolve_measure_falls_back_to_available_action():
    measure = resolve_measure(
        "Compare les ventes sur 2 mois",
        available_actions={"consulter_facturation"},
    )
    assert measure["recommended_action"] == "consulter_facturation"
