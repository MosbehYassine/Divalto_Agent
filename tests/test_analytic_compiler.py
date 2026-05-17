import os
import sys

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import pytest  # noqa: E402

from analytic_compiler import compile_mdx, compile_sqlite, validate_plan  # noqa: E402


@pytest.fixture()
def sample_table_meta():
    return {
        "table": "sales",
        "dimensions": [
            {"name": "region", "kind": "attribute"},
            {"name": "sale_date", "kind": "date"},
        ],
        "measures": [
            {"name": "amount", "aggregation": "sum"},
            {"name": "price", "aggregation": "avg"},
        ],
    }


def test_validate_and_compile_sql_grouped(sample_table_meta):
    raw = {
        "table": "sales",
        "measures": [{"name": "amount", "aggregation": "sum"}],
        "dimensions": ["region"],
        "filters": [{"column": "region", "op": "=", "value": "N"}],
        "order": "desc",
        "limit": 5,
    }
    plan = validate_plan(raw, sample_table_meta)
    sql, params = compile_sqlite(plan)
    assert sql.lower().startswith("select")
    assert "group by" in sql.lower()
    assert params == ["N"]
    assert "LIMIT 5" in sql


def test_compile_mdx_grand_total(sample_table_meta):
    raw = {
        "table": "sales",
        "measures": [{"name": "amount", "aggregation": "sum"}],
        "dimensions": [],
    }
    plan = validate_plan(raw, sample_table_meta)
    mdx = compile_mdx(plan, "TestCube")
    assert "FROM [TestCube]" in mdx
    assert "[Measures].[amount_sum]" in mdx
    assert "ON ROWS" not in mdx


def test_compile_mdx_cross_dims(sample_table_meta):
    raw = {
        "table": "sales",
        "measures": [{"name": "amount", "aggregation": "sum"}],
        "dimensions": ["region", "sale_date"],
        "date_grain": "month",
    }
    plan = validate_plan(raw, sample_table_meta)
    mdx = compile_mdx(plan, "AutoCube")
    assert "[sales].[region].MEMBERS" in mdx
    assert "[sales].[sale_date].MEMBERS" in mdx
    assert "*" in mdx or "CROSSJOIN" in mdx.upper() or "{" in mdx


def test_reject_unknown_measure(sample_table_meta):
    raw = {
        "table": "sales",
        "measures": [{"name": "unknown", "aggregation": "sum"}],
        "dimensions": [],
    }
    with pytest.raises(ValueError, match="not allowed"):
        validate_plan(raw, sample_table_meta)
