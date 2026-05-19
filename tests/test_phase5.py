"""
Tests orchestration Phase 5 without requiring SQLite or remote endpoints.
"""

import os
import sys

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from phase5.agent import run_phase5_structured  # noqa: E402
from phase5.analytics import synthesize_answer  # noqa: E402


def test_phase5_classement_plus_total_fr():
    query = "Top 3 des références sur les 10 derniers jours avec CA total consolidé."
    mocks = {
        "step_0": {
            "items": [
                {"rank": 1, "reference": "ART-A", "quantite": 12, "ca": "120.50"},
                {"rank": 2, "reference": "ART-B", "quantite": 10, "ca": "80.25"},
                {"rank": 3, "reference": "ART-C", "quantite": 4, "ca": "40.10"},
            ],
            "leaderReference": "ART-A",
            "startDate": "20250423",
            "endDate": "20260503",
        },
        "step_1": {"totalVentes": 240.85},
    }
    structured = run_phase5_structured(query, mock_responses=mocks)
    assert structured["plan"][0]["action"] == "classement_ventes"
    assert structured["plan"][1]["action"] == "consulter_ventes"
    answer = structured["answer"]
    assert "ART-A" in answer
    assert "Synthèse tableau" in answer
    assert "CA consolidé" in answer


def test_phase5_stock_followup():
    query = "Quel est le produit le plus vendu et quel est son stock ?"
    mocks = {
        "step_0": {
            "items": [{"rank": 1, "reference": "HERO", "quantite": 333, "ca": "5000"}],
            "leaderReference": "HERO",
        },
        "step_1": {"reference": "HERO", "warehouse": "*", "quantity": 42},
    }
    structured = run_phase5_structured(query, mock_responses=mocks)
    answer = structured["answer"]
    assert "HERO" in answer and "42" in answer


def test_phase5_dual_period_comparison():
    query = "Compare les ventes des 14 derniers jours face à la fenêtre précédente."
    fake_steps = [
        {
            "ok": True,
            "action": "consulter_ventes",
            "payload_snapshot": {"startDate": "20250419", "endDate": "20260503"},
            "raw": {"totalVentes": 48200},
        },
        {
            "ok": True,
            "action": "consulter_ventes",
            "payload_snapshot": {"startDate": "20250405", "endDate": "20250418"},
            "raw": {"totalVentes": 41500},
        },
    ]
    stitched = synthesize_answer(query, {"steps": fake_steps, "errors": [], "memory": {}, "ok": True})
    assert "Δ" in stitched or "+" in stitched
    assert "Comparaison" in stitched


def test_phase5_indicateurs_series():
    stitched = synthesize_answer(
        "Montre moi l'évolution des ventes par mois lors des 180 derniers jours.",
        {
            "steps": [
                {
                    "ok": True,
                    "action": "consulter_indicateurs_analytiques",
                    "payload_snapshot": {
                        "metric": "sales",
                        "groupBy": "month",
                        "startDate": "20250401",
                        "endDate": "20260503",
                    },
                    "raw": {
                        "metric": "sales",
                        "groupBy": "month",
                        "series": [
                            {"bucket": "2025-04", "value": 1200.5},
                            {"bucket": "2025-05", "value": 900.25},
                            {"bucket": "2025-06", "value": 650.75},
                        ],
                    },
                }
            ]
        },
    )
    assert "Répartition" in stitched or "Indicateurs" in stitched
