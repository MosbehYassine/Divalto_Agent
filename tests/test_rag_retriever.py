import os
import sys
from pathlib import Path

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import rag_retriever as rag  # noqa: E402


def test_retrieve_context_returns_relevant_snippet(tmp_path: Path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "kpi.md").write_text(
        "Le chiffre d'affaires mensuel doit etre compare au mois precedent.",
        encoding="utf-8",
    )
    (docs / "stock.md").write_text(
        "Le stock disponible est suivi par depot et reference article.",
        encoding="utf-8",
    )
    monkeypatch.setattr(rag, "RAG_ENABLED", True)
    monkeypatch.setattr(rag, "RAG_DOCS_DIR", str(docs))
    rag._INDEX_CACHE["root"] = None
    rag._INDEX_CACHE["signature"] = None
    rag._INDEX_CACHE["chunks"] = []

    out = rag.retrieve_context("compare le chiffre d'affaires mensuel", top_k=1)
    assert out["enabled"] is True
    assert len(out["snippets"]) == 1
    assert "chiffre" in out["snippets"][0]["text"].lower()


def test_retrieve_context_disabled(monkeypatch):
    monkeypatch.setattr(rag, "RAG_ENABLED", False)
    out = rag.retrieve_context("any query")
    assert out["enabled"] is False
    assert out["context"] == ""
