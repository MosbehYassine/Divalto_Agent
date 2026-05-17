"""
auto_olap_pipeline.py
=====================
Automatic semantic model + cube artifact generator for unseen ERP datasets.

This module profiles source data, infers dimensions/measures/hierarchies,
and generates:
- semantic_model.json
- mdx_templates.json
- cube_tmsl.json (authoring skeleton)
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ColumnMeta:
    name: str
    db_type: str
    nullable: bool


def _domain_from_table_name(table_name: str) -> str:
    name = table_name.lower()
    if any(k in name for k in ("sale", "vente", "order", "commande")):
        return "sales"
    if any(k in name for k in ("purch", "achat", "supplier", "fourn")):
        return "purchases"
    if any(k in name for k in ("stock", "invent", "warehouse", "depot")):
        return "inventory"
    if any(k in name for k in ("invoice", "factur", "billing")):
        return "finance"
    if any(k in name for k in ("client", "customer", "crm")):
        return "crm"
    return "generic"


def _is_numeric_type(db_type: str) -> bool:
    t = db_type.lower()
    return any(k in t for k in ("int", "real", "float", "double", "numeric", "decimal"))


def _is_date_like(col_name: str, db_type: str) -> bool:
    n = col_name.lower()
    t = db_type.lower()
    return any(k in n for k in ("date", "time", "jour", "mois", "annee")) or any(
        k in t for k in ("date", "time")
    )


def _is_identifier(col_name: str) -> bool:
    n = col_name.lower()
    return n.endswith("id") or n.endswith("_id") or "code" in n or "key" in n


def _guess_agg(col_name: str) -> str:
    n = col_name.lower()
    if any(k in n for k in ("price", "unit", "rate", "ratio", "avg", "moy")):
        return "avg"
    return "sum"


def _profile_sqlite(source_db: Path) -> dict[str, list[ColumnMeta]]:
    conn = sqlite3.connect(str(source_db))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [r[0] for r in cur.fetchall()]
    result: dict[str, list[ColumnMeta]] = {}
    for table in tables:
        cur.execute(f"PRAGMA table_info('{table}')")
        cols = []
        for row in cur.fetchall():
            # row = cid, name, type, notnull, dflt_value, pk
            cols.append(ColumnMeta(name=row[1], db_type=row[2] or "TEXT", nullable=row[3] == 0))
        result[table] = cols
    conn.close()
    return result


def infer_semantic_model(source_db: str) -> dict[str, Any]:
    tables = _profile_sqlite(Path(source_db))
    model_tables: list[dict[str, Any]] = []
    for table_name, cols in tables.items():
        measures: list[dict[str, Any]] = []
        dimensions: list[dict[str, Any]] = []
        hierarchies: list[dict[str, Any]] = []

        for col in cols:
            if _is_date_like(col.name, col.db_type):
                dimensions.append({"name": col.name, "kind": "date"})
                hierarchies.append(
                    {
                        "name": f"{col.name}_hierarchy",
                        "levels": ["Year", "Quarter", "Month", "Day"],
                    }
                )
                continue
            if _is_numeric_type(col.db_type) and not _is_identifier(col.name):
                measures.append(
                    {
                        "name": col.name,
                        "aggregation": _guess_agg(col.name),
                        "data_type": col.db_type,
                    }
                )
                continue
            dimensions.append(
                {
                    "name": col.name,
                    "kind": "identifier" if _is_identifier(col.name) else "attribute",
                }
            )

        dim_names = {d["name"].lower() for d in dimensions}
        if {"country", "region", "city"}.issubset(dim_names):
            hierarchies.append(
                {"name": "geography_hierarchy", "levels": ["country", "region", "city"]}
            )

        model_tables.append(
            {
                "table": table_name,
                "domain": _domain_from_table_name(table_name),
                "dimensions": dimensions,
                "measures": measures,
                "hierarchies": hierarchies,
            }
        )

    return {"source": str(source_db), "tables": model_tables}


def generate_mdx_templates(semantic_model: dict[str, Any]) -> dict[str, Any]:
    templates: list[dict[str, str]] = []
    for table in semantic_model.get("tables", []):
        table_name = table["table"]
        first_dim = next((d for d in table.get("dimensions", []) if d.get("kind") != "identifier"), None)
        for measure in table.get("measures", []):
            m = measure["name"]
            templates.append(
                {
                    "name": f"{table_name}_{m}_total",
                    "query": (
                        "SELECT {[Measures].[" + m + "]} ON COLUMNS "
                        "FROM [AutoCube]"
                    ),
                }
            )
            if first_dim:
                d = first_dim["name"]
                templates.append(
                    {
                        "name": f"{table_name}_{m}_by_{d}",
                        "query": (
                            "SELECT {[Measures].[" + m + "]} ON COLUMNS, "
                            "NON EMPTY ["
                            + table_name
                            + "].["
                            + d
                            + "].MEMBERS ON ROWS "
                            "FROM [AutoCube]"
                        ),
                    }
                )
    return {"templates": templates}


def generate_tmsl_skeleton(semantic_model: dict[str, Any], db_name: str = "AutoCubeModel") -> dict[str, Any]:
    tables_payload = []
    for table in semantic_model.get("tables", []):
        columns = []
        for d in table.get("dimensions", []):
            columns.append({"name": d["name"], "dataType": "string"})
        for m in table.get("measures", []):
            columns.append({"name": m["name"], "dataType": "double"})
        tables_payload.append(
            {
                "name": table["table"],
                "columns": columns,
                "measures": [
                    {
                        "name": f"{m['name']}_{m['aggregation']}",
                        "expression": f"{m['aggregation'].upper()}([{m['name']}])",
                        "formatString": "#,0.00",
                    }
                    for m in table.get("measures", [])
                ],
            }
        )
    return {
        "createOrReplace": {
            "object": {"database": db_name},
            "database": {"name": db_name, "compatibilityLevel": 1500, "model": {"tables": tables_payload}},
        }
    }


def run_auto_modeling(source_db: str, output_dir: str) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    semantic_model = infer_semantic_model(source_db)
    mdx_templates = generate_mdx_templates(semantic_model)
    tmsl = generate_tmsl_skeleton(semantic_model)

    semantic_path = out / "semantic_model.json"
    mdx_path = out / "mdx_templates.json"
    tmsl_path = out / "cube_tmsl.json"

    semantic_path.write_text(json.dumps(semantic_model, ensure_ascii=False, indent=2), encoding="utf-8")
    mdx_path.write_text(json.dumps(mdx_templates, ensure_ascii=False, indent=2), encoding="utf-8")
    tmsl_path.write_text(json.dumps(tmsl, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "semantic_model": str(semantic_path),
        "mdx_templates": str(mdx_path),
        "cube_tmsl": str(tmsl_path),
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Auto-generate OLAP model and MDX templates from ERP source data.")
    p.add_argument("--source-sqlite", required=True, help="Path to source SQLite database.")
    p.add_argument("--output-dir", required=True, help="Directory to write generated model artifacts.")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    artifacts = run_auto_modeling(args.source_sqlite, args.output_dir)
    print(json.dumps(artifacts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
