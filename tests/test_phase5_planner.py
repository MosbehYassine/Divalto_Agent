import os
import sys

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from phase5_planner import phase5_mock_plan  # noqa: E402
import phase5_planner as planner_mod  # noqa: E402


def test_phase5_classement_structure():
    plan = phase5_mock_plan("Donne le top 3 des produits sur les 7 derniers jours")
    assert plan[0]["action"] == "classement_ventes"
    assert plan[0]["limit"] == 3


def test_phase5_comparison_emits_two_ventes_calls():
    plan = phase5_mock_plan("Compare vite avec versus la période précédente (vue agrégée seulement)")
    actions = [s["action"] for s in plan]
    assert actions.count("consulter_ventes") == 2


def test_phase5_indicateurs_for_mensuel_keyword():
    plan = phase5_mock_plan("Montre l'évolution mensuelle des ventes")
    assert plan[0]["action"] == "consulter_indicateurs_analytiques"
    assert plan[0]["groupBy"] == "month"


def test_phase5_comparison_falls_back_to_facturation_when_sales_missing(monkeypatch):
    monkeypatch.setattr(
        planner_mod,
        "get_available_actions",
        lambda: {"consulter_facturation", "consulter_indicateurs_analytiques"},
    )
    plan = phase5_mock_plan("Compare les ventes de ce mois vs le mois dernier")
    actions = [s["action"] for s in plan]
    assert actions.count("consulter_facturation") == 2
