"""
analytic_catalog.py
===================
Load or materialize semantic_model.json (and optional mdx_templates.json)
for schema-bound analytics — no cube/table names are hardcoded in business logic.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from settings import AUTO_GENERATE_SEMANTIC_FROM_SQLITE, SEMANTIC_MODEL_DIR, SQLITE_MOCK_DB_PATH


def default_semantic_dir() -> Path:
    """Default: agent_project/generated_olap next to this package."""
    return Path(__file__).resolve().parent.parent / "generated_olap"


def resolve_semantic_dir() -> Path:
    raw = (SEMANTIC_MODEL_DIR or "").strip()
    return Path(raw) if raw else default_semantic_dir()


def load_semantic_model(semantic_dir: Path) -> dict[str, Any] | None:
    path = semantic_dir / "semantic_model.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def load_mdx_templates(semantic_dir: Path) -> dict[str, Any] | None:
    path = semantic_dir / "mdx_templates.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def ensure_semantic_from_sqlite(semantic_dir: Path, sqlite_path: Path) -> dict[str, Any] | None:
    """
    If semantic_model.json is missing, run auto_olap_pipeline on sqlite_path.
    Returns loaded semantic model or None.
    """
    if not AUTO_GENERATE_SEMANTIC_FROM_SQLITE:
        return None
    if not sqlite_path.is_file():
        return None
    semantic_dir.mkdir(parents=True, exist_ok=True)
    from auto_olap_pipeline import run_auto_modeling

    run_auto_modeling(str(sqlite_path), str(semantic_dir))
    return load_semantic_model(semantic_dir)


def load_or_build_semantic_bundle() -> tuple[dict[str, Any] | None, Path, list[str]]:
    """
    Returns (bundle_or_none, semantic_dir, notes).

    bundle shape: {"semantic_model": dict, "mdx_templates": dict | None}
    """
    notes: list[str] = []
    semantic_dir = resolve_semantic_dir()
    model = load_semantic_model(semantic_dir)
    sqlite_raw = (os.getenv("DIVALTO_SQLITE_DB_PATH") or "").strip() or (SQLITE_MOCK_DB_PATH or "").strip()
    if model is None and sqlite_raw:
        sqlite_path = Path(sqlite_raw)
        notes.append(f"semantic_model.json missing under {semantic_dir}; attempting infer from SQLite.")
        model = ensure_semantic_from_sqlite(semantic_dir, sqlite_path)
        if model:
            notes.append(f"Inferred semantic model from {sqlite_path}.")
        else:
            notes.append("Could not infer semantic model (SQLite missing or generation disabled).")
    templates = load_mdx_templates(semantic_dir) if model else None
    if not model:
        return None, semantic_dir, notes
    return {"semantic_model": model, "mdx_templates": templates}, semantic_dir, notes


def catalog_for_llm(semantic_model: dict[str, Any]) -> dict[str, Any]:
    """Minimal schema description for the planner (identifiers only from data)."""
    tables_out: list[dict[str, Any]] = []
    for t in semantic_model.get("tables", []):
        if not isinstance(t, dict):
            continue
        name = t.get("table")
        if not isinstance(name, str) or not name.strip():
            continue
        dims: list[dict[str, str]] = []
        for d in t.get("dimensions", []) or []:
            if isinstance(d, dict) and isinstance(d.get("name"), str):
                dims.append({"name": d["name"], "kind": str(d.get("kind", "attribute"))})
        measures: list[dict[str, str]] = []
        for m in t.get("measures", []) or []:
            if isinstance(m, dict) and isinstance(m.get("name"), str):
                measures.append(
                    {
                        "name": m["name"],
                        "aggregation": str(m.get("aggregation", "sum")).lower(),
                    }
                )
        tables_out.append({"table": name, "dimensions": dims, "measures": measures})
    return {"tables": tables_out}


def index_tables(semantic_model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for t in semantic_model.get("tables", []) or []:
        if isinstance(t, dict) and isinstance(t.get("table"), str):
            by_name[t["table"]] = t
    return by_name
