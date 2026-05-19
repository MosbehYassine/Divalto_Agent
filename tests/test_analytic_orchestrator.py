import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


@pytest.fixture()
def tiny_semantic_bundle(tmp_path: Path):
    db = tmp_path / "mini.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE sales (region TEXT, amount REAL);")
    conn.execute("INSERT INTO sales VALUES ('N', 10.0), ('S', 25.0), ('N', 5.0);")
    conn.commit()
    conn.close()

    semantic = {
        "source": str(db),
        "tables": [
            {
                "table": "sales",
                "domain": "sales",
                "dimensions": [{"name": "region", "kind": "attribute"}],
                "measures": [{"name": "amount", "aggregation": "sum", "data_type": "REAL"}],
                "hierarchies": [],
            }
        ],
    }
    (tmp_path / "semantic_model.json").write_text(
        __import__("json").dumps(semantic, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return tmp_path, db


def test_run_semantic_data_analytics_executes_sqlite(monkeypatch, tiny_semantic_bundle):
    tmp_path, db = tiny_semantic_bundle

    def fake_bundle():
        model = __import__("json").loads((tmp_path / "semantic_model.json").read_text(encoding="utf-8"))
        return {"semantic_model": model, "mdx_templates": None}, tmp_path, []

    def fake_ollama(**_kwargs):
        return {
            "table": "sales",
            "measures": [{"name": "amount", "aggregation": "sum"}],
            "dimensions": ["region"],
            "filters": [],
            "order": "desc",
            "limit": 10,
        }

    monkeypatch.setenv("DIVALTO_USE_SQLITE_MOCK", "1")
    monkeypatch.setenv("DIVALTO_SQLITE_DB_PATH", str(db))
    monkeypatch.setenv("DIVALTO_OLAP_CUBE_NAME", "MiniCube")

    with patch("analytic_orchestrator.load_or_build_semantic_bundle", fake_bundle):
        with patch("analytic_orchestrator.call_ollama_json_object", fake_ollama):
            from analytics.orchestrator import run_semantic_data_analytics

            out = run_semantic_data_analytics("total sales by region")

    assert out["ok"] is True
    assert out["executed_sqlite"] is True
    assert "MiniCube" in out["mdx"]
    assert "GROUP BY" in out["sql"].upper()
    assert "N" in out["answer"] or "25" in out["answer"] or "S" in out["answer"]


def test_run_semantic_data_analytics_mdx_remote_section(monkeypatch, tiny_semantic_bundle):
    tmp_path, db = tiny_semantic_bundle

    def fake_bundle():
        model = __import__("json").loads((tmp_path / "semantic_model.json").read_text(encoding="utf-8"))
        return {"semantic_model": model, "mdx_templates": None}, tmp_path, []

    def fake_ollama(**_kwargs):
        return {
            "table": "sales",
            "measures": [{"name": "amount", "aggregation": "sum"}],
            "dimensions": [],
            "filters": [],
        }

    def fake_mdx_execute(mdx: str, **_kwargs):
        return {
            "ok": True,
            "skipped": False,
            "headers": ["Amount"],
            "rows": [(99.0,)],
            "truncated": False,
            "max_rows": 500,
        }

    monkeypatch.setenv("DIVALTO_USE_SQLITE_MOCK", "0")
    monkeypatch.setenv("DIVALTO_MDX_EXECUTE_ENABLED", "true")
    monkeypatch.setenv("DIVALTO_MDX_CONNECTION_STRING", "Provider=MSOLAP;Data Source=stub;")

    with patch("analytic_orchestrator.load_or_build_semantic_bundle", fake_bundle):
        with patch("analytic_orchestrator.call_ollama_json_object", fake_ollama):
            with patch("analytic_orchestrator.execute_mdx_cellset", fake_mdx_execute):
                from analytics.orchestrator import run_semantic_data_analytics

                out = run_semantic_data_analytics("grand total sales")

    assert out.get("executed_mdx_remote") is True
    assert "moteur OLAP distant" in out["answer"]
    assert "99" in out["answer"]
