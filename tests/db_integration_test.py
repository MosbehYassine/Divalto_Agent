"""
End-to-end integration checks using sqlite mock database as ERP source.

Run:
    python tests/db_integration_test.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Configure sqlite backend BEFORE importing runtime modules.
DB_PATH = (ROOT_DIR.parent / "mock database" / "magasin_mock.db").resolve()
os.environ["DIVALTO_USE_SQLITE_MOCK"] = "1"
os.environ["DIVALTO_SQLITE_DB_PATH"] = str(DB_PATH)

from core.divalto_agent import run_agent, run_agent_structured  # noqa: E402
from phase3.agent import run_phase3  # noqa: E402
from phase4.agent import run_phase4  # noqa: E402


def _assert(name: str, condition: bool, details: str) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name} -> {details}")
    if not condition:
        raise AssertionError(name)


def test_phase2() -> None:
    print("\n=== PHASE 2 (DB-backed) ===")
    stock_answer = run_agent({"action": "interroger_stock", "reference": "Clavier", "warehouse": "*"})
    _assert("Stock query", "stock" in stock_answer.lower(), stock_answer)

    top_answer = run_agent({"action": "article_plus_vendu"})
    _assert("Top seller query", "plus vendu" in top_answer.lower(), top_answer)

    facture_answer = run_agent({"action": "consulter_facturation"})
    _assert("Facturation query", "facturation" in facture_answer.lower(), facture_answer)

    create_piece = run_agent({"action": "integrer_piece", "pieceType": "FA", "customerType": "CLI", "customer": "CLI-001"})
    _assert("Integrer piece", "id" in create_piece.lower(), create_piece)


def test_phase3() -> None:
    print("\n=== PHASE 3 (DB-backed orchestrator) ===")
    q1 = run_phase3("Quel est le stock de l'article Clavier ?", use_mock_planner=True, mock_responses=None)
    _assert("Phase3 stock", "stock" in q1.lower(), q1)

    q2 = run_phase3(
        "Quel est l'article le plus vendu et quel est son stock ?",
        use_mock_planner=True,
        mock_responses=None,
    )
    _assert("Phase3 top+stock", "stock actuel" in q2.lower() or "plus vendu" in q2.lower(), q2)

    q3 = run_phase3("Compare les ventes de ce mois vs le mois dernier", use_mock_planner=True, mock_responses=None)
    _assert("Phase3 comparison", "évolution" in q3.lower() or "mois" in q3.lower(), q3)


def test_phase4_to_phase2_execution() -> None:
    print("\n=== PHASE 4 (payload) + EXECUTION ===")
    phase4 = run_phase4("Donne la facturation entre 20240101 et 20241231")
    _assert("Phase4 output shape", "tools" in phase4 and "diagnostics" in phase4, str(phase4.get("ok")))

    if phase4.get("ok") and phase4.get("payload"):
        exec_result = run_agent_structured(phase4["payload"])
        _assert("Phase4 payload executable", exec_result.get("ok", False), str(exec_result))
    else:
        # Clarification is allowed by phase4 guards; this still confirms gate behavior.
        _assert("Phase4 guard active", phase4.get("requires_clarification", False), phase4.get("clarification_message", ""))


def main() -> int:
    print("=" * 64)
    print("DB INTEGRATION TEST SUITE")
    print(f"SQLite source: {DB_PATH}")
    print("=" * 64)
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    test_phase2()
    test_phase3()
    test_phase4_to_phase2_execution()

    print("\nAll DB integration tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
