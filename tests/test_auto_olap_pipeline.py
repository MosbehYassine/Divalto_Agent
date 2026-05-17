import os
import sqlite3
import sys
from pathlib import Path

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from auto_olap_pipeline import (  # noqa: E402
    generate_mdx_templates,
    infer_semantic_model,
    run_auto_modeling,
)


def _build_demo_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE sales_orders (
            order_id INTEGER PRIMARY KEY,
            customer_code TEXT,
            sale_date TEXT,
            amount REAL,
            quantity INTEGER,
            country TEXT,
            region TEXT,
            city TEXT
        )
        """
    )
    cur.execute(
        """
        INSERT INTO sales_orders (customer_code, sale_date, amount, quantity, country, region, city)
        VALUES ('CLI-001', '2026-05-01', 100.5, 2, 'TN', 'NORD', 'Tunis')
        """
    )
    conn.commit()
    conn.close()


def test_infer_semantic_model_detects_measures_and_hierarchy(tmp_path: Path):
    db_path = tmp_path / "demo.db"
    _build_demo_db(db_path)
    model = infer_semantic_model(str(db_path))
    assert model["tables"]
    table = model["tables"][0]
    measure_names = {m["name"] for m in table["measures"]}
    assert "amount" in measure_names
    assert "quantity" in measure_names
    hierarchy_names = {h["name"] for h in table["hierarchies"]}
    assert "sale_date_hierarchy" in hierarchy_names
    assert "geography_hierarchy" in hierarchy_names


def test_generate_mdx_templates_for_measures(tmp_path: Path):
    db_path = tmp_path / "demo.db"
    _build_demo_db(db_path)
    model = infer_semantic_model(str(db_path))
    mdx = generate_mdx_templates(model)
    assert len(mdx["templates"]) >= 2
    assert any("Measures].[amount" in t["query"] for t in mdx["templates"])


def test_run_auto_modeling_writes_artifacts(tmp_path: Path):
    db_path = tmp_path / "demo.db"
    _build_demo_db(db_path)
    out = tmp_path / "artifacts"
    artifacts = run_auto_modeling(str(db_path), str(out))
    for file_path in artifacts.values():
        p = Path(file_path)
        assert p.exists()
        assert p.read_text(encoding="utf-8").strip()
