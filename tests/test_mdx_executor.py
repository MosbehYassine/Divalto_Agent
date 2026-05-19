import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_SRC_DIR = _TESTS_DIR.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from analytics.mdx_executor import execute_mdx_cellset, mdx_looks_read_only, should_execute_mdx_remote  # noqa: E402


def test_mdx_looks_read_only_accepts_select_and_with():
    assert mdx_looks_read_only("SELECT {} ON 0 FROM [X]")
    assert mdx_looks_read_only("WITH MEMBER ... SELECT ...")


def test_mdx_looks_read_only_rejects_dml():
    assert not mdx_looks_read_only("SELECT 1; DROP TABLE x")
    assert not mdx_looks_read_only("INSERT INTO x VALUES (1)")


def test_execute_mdx_skips_without_connection(monkeypatch):
    monkeypatch.delenv("DIVALTO_MDX_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("DIVALTO_MDX_EXECUTE_ENABLED", raising=False)
    r = execute_mdx_cellset("SELECT 1 ON 0 FROM [Cube]", connection_string="")
    assert r["skipped"] is True
    assert r["reason"] == "no_connection_string"


def test_should_execute_mdx_remote_requires_both(monkeypatch):
    monkeypatch.setenv("DIVALTO_MDX_EXECUTE_ENABLED", "true")
    monkeypatch.delenv("DIVALTO_MDX_CONNECTION_STRING", raising=False)
    assert should_execute_mdx_remote() is False

    monkeypatch.setenv("DIVALTO_MDX_CONNECTION_STRING", "Provider=MSOLAP;...")
    assert should_execute_mdx_remote() is True
