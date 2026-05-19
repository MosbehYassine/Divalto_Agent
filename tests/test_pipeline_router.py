import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parents[1] / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from core.pipeline_router import resolve_execution_mode


def test_mdx_query_routes_phase4():
    q = "Requête MDX cube : quantités vendues par article"
    assert resolve_execution_mode(q) == "phase4"


def test_breakdown_without_mdx_stays_classic():
    q = "Chiffre d'affaires par ville pour les clients"
    assert resolve_execution_mode(q) == "classic"
