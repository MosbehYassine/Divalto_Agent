import os
import sys

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from core.intent_contract import infer_intent  # noqa: E402
from app.server import _infer_mode_from_query  # noqa: E402


def test_client_total_question_not_kpi_analysis():
    q = "Combien au total des clients (somme globale)?"
    assert infer_intent(q).intent == "generic_business_query"


def test_client_count_routes_to_classic_mode():
    assert _infer_mode_from_query("Combien au total des clients ?") == "classic"
    assert _infer_mode_from_query("Nombre de clients dans la base") == "classic"
