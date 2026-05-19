"""
SQLite-backed classement regression — skipped when ``magasin_mock.db`` absent.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAGASIN_DB = (ROOT.parent / "mock database" / "magasin_mock.db").resolve()
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.mark.skipif(not MAGASIN_DB.exists(), reason=f"SQLite fixture missing: {MAGASIN_DB}")
def test_sqlite_classement_returns_structure():
    os.environ["DIVALTO_USE_SQLITE_MOCK"] = "1"
    os.environ["DIVALTO_SQLITE_DB_PATH"] = str(MAGASIN_DB)

    from core.sqlite_backend import execute_action  # noqa: E402

    payload = execute_action(
        "classement_ventes",
        {"startDate": "19000101", "endDate": "99991231", "limit": 3},
        str(MAGASIN_DB),
    )
    assert "items" in payload
    assert isinstance(payload["items"], list)
