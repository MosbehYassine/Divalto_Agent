"""
analytic_orchestrator.py
========================
Turn natural-language data questions into catalog-validated plans,
compile MDX + SQLite SQL, execute read-only against the mock DB when available,
and return a user-facing narrative (no hardcoded business rules).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from typing import Any

from analytics.catalog import catalog_for_llm, index_tables, load_or_build_semantic_bundle
from analytics.compiler import compile_mdx, compile_sqlite, validate_plan
from analytics.mdx_executor import execute_mdx_cellset, should_execute_mdx_remote
from llm.ollama_client import call_ollama_json_object
from core.settings import OLLAMA_ANALYTIC_NUM_PREDICT, OLLAMA_ANALYTIC_TIMEOUT_SECONDS


def _runtime_sqlite_mock_path() -> str:
    """Read at call time so tests and subprocesses can toggle env without reloading settings."""
    return (os.getenv("DIVALTO_SQLITE_DB_PATH") or "").strip()


def _runtime_use_sqlite_mock() -> bool:
    raw = (os.getenv("DIVALTO_USE_SQLITE_MOCK") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _runtime_cube_name() -> str:
    v = (os.getenv("DIVALTO_OLAP_CUBE_NAME") or "").strip()
    return v or "AutoCube"


def _build_system_prompt(catalog: dict[str, Any]) -> str:
    catalog_json = json.dumps(catalog, ensure_ascii=False, indent=2)
    return f"""You are an analytics planner. Your job is to map the user's question to a JSON query plan
against the ONLY tables/measures/dimensions listed in the catalog below. Do not invent columns or tables.

Catalog (authorized schema):
{catalog_json}

Output a single JSON object with exactly these keys:
- "table" (string): one of the catalog table names.
- "measures" (array): objects with "name" and "aggregation" matching catalog entries exactly.
- "dimensions" (array of strings): subset of that table's dimension names; can be empty for totals.
- "filters" (array): optional objects {{"column", "op", "value"}} where op is one of =, !=, <, >, <=, >=, like, in.
  For "in", use "value" as an array of literals.
- "order" (optional): "asc" or "desc" — applies to the first measure when grouping.
- "limit" (optional): positive integer cap on rows (max 10000).
- "date_grain" (optional): when grouping by a date dimension, one of day, month, year (default month).

Rules:
- Prefer the smallest set of dimensions that answers the question.
- Use measures and dimensions exactly as named in the catalog (case-sensitive).
- Respond with JSON only — no markdown fences, no commentary outside the JSON object.
"""


def _execute_sqlite_readonly(db_path: str, sql: str, params: list[Any]) -> tuple[list[str], list[tuple[Any, ...]]]:
    if not sql.strip().lower().startswith("select"):
        raise ValueError("Only SELECT statements may be executed.")
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        cur = conn.execute(sql, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        return cols, rows
    finally:
        conn.close()


def _wants_sales_by_article(user_query: str) -> bool:
    q = user_query.lower()
    by_article = bool(
        re.search(
            r"\b(par|by|regroup\w*\s+par|grouped\s+by)\s+(article|produit|designation|désignation)s?\b",
            q,
        )
    )
    if not by_article:
        return False
    return bool(
        re.search(
            r"quantit|volume|unit|vente|chiffre|affaire|\bca\b|sales|mdx|olap|cube",
            q,
        )
    )


def _metric_for_sales_by_article(user_query: str) -> str:
    q = user_query.lower()
    if any(w in q for w in ("chiffre", "affaire", " ca ", "ca ", "revenue", "montant")) and not re.search(
        r"quantit|volume|unit", q
    ):
        return "sales"
    return "quantity"


def _build_sales_by_article_queries(metric: str, cube: str) -> tuple[str, str, str]:
    if metric == "quantity":
        value_expr = "SUM(v.quantite)"
        measure_mdx = "quantite_sum"
        label = "Quantités vendues"
    else:
        value_expr = "SUM(v.quantite * v.prix_vente_unitaire)"
        measure_mdx = "quantite_sum"
        label = "Chiffre d'affaires (SQL : somme quantité × prix unitaire)"
    sql = f"""
SELECT
    a.designation AS article,
    ROUND(COALESCE({value_expr}, 0), 2) AS value
FROM ventes v
JOIN articles a ON a.id = v.id_article
JOIN factures f ON f.id = v.id_facture
GROUP BY a.id, a.designation
ORDER BY value DESC
""".strip()
    mdx = (
        f"SELECT {{ [Measures].[{measure_mdx}] }} ON COLUMNS,\n"
        f"NON EMPTY [articles].[designation].MEMBERS ON ROWS\n"
        f"FROM [{cube}]"
    )
    return sql, mdx, label


def _finalize_analytic_answer(
    *,
    mdx: str,
    sql: str,
    sql_params: list[Any] | None = None,
    cube: str,
) -> tuple[str, bool, bool]:
    """Build markdown answer + execution flags."""
    narrative_parts = [
        "### Résultat analytique",
        "",
        "Requête **MDX** générée (alignée sur le cube et le libellé article) :",
        "",
        "```mdx",
        mdx,
        "```",
        "",
        "Équivalent **SQLite** exécuté en lecture seule (aperçu des données) :",
        "",
        "```sql",
        sql,
        "```",
        "",
    ]
    executed_sqlite = False
    executed_mdx_remote = False
    params = sql_params or []

    if _runtime_use_sqlite_mock() and _runtime_sqlite_mock_path():
        db_path = _runtime_sqlite_mock_path()
        try:
            headers, rows = _execute_sqlite_readonly(db_path, sql, params)
            executed_sqlite = True
            narrative_parts.append("### Données")
            narrative_parts.append("")
            narrative_parts.append(_rows_to_markdown(headers, rows))
        except Exception as exc:  # noqa: BLE001
            narrative_parts.append(f"_Exécution SQLite impossible : {exc}_")
    else:
        narrative_parts.append(
            "_Activez `DIVALTO_USE_SQLITE_MOCK=true` et `DIVALTO_SQLITE_DB_PATH` pour exécuter l'aperçu SQL._"
        )

    if should_execute_mdx_remote():
        mdx_remote = execute_mdx_cellset(mdx)
        if mdx_remote.get("ok"):
            executed_mdx_remote = True
            rh = mdx_remote.get("headers") or []
            rr = mdx_remote.get("rows") or []
            narrative_parts.append("### Résultat MDX (moteur OLAP distant)")
            narrative_parts.append("")
            narrative_parts.append(_rows_to_markdown(rh, rr))
            if mdx_remote.get("truncated"):
                narrative_parts.append("\n_Résultat tronqué (plafond `DIVALTO_MDX_MAX_ROWS`)._")
        elif not mdx_remote.get("skipped"):
            err = mdx_remote.get("error") or mdx_remote.get("reason") or "erreur inconnue"
            narrative_parts.append(f"_Exécution MDX distante impossible : {err}_")

    return "\n".join(narrative_parts).strip(), executed_sqlite, executed_mdx_remote


def _run_sales_by_article_analytic(user_query: str, cube: str) -> dict[str, Any]:
    metric = _metric_for_sales_by_article(user_query)
    sql, mdx, label = _build_sales_by_article_queries(metric, cube)
    answer, executed_sqlite, executed_mdx_remote = _finalize_analytic_answer(
        mdx=mdx, sql=sql, sql_params=[], cube=cube
    )
    return {
        "ok": True,
        "plan": {
            "table": "ventes",
            "measures": [{"name": "quantite", "aggregation": "sum"}],
            "dimensions": ["article_designation"],
            "deterministic": "sales_by_article",
        },
        "sql": sql,
        "sql_params": [],
        "mdx": mdx,
        "cube": cube,
        "metric_label": label,
        "executed_sqlite": executed_sqlite,
        "executed_mdx_remote": executed_mdx_remote,
        "answer": answer,
    }


def _rows_to_markdown(headers: list[str], rows: list[tuple[Any, ...]], max_rows: int = 50) -> str:
    if not headers:
        return "_No columns returned._"
    display = rows[:max_rows]
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body_lines = ["| " + " | ".join("" if v is None else str(v) for v in r) + " |" for r in display]
    tail = f"\n\n_Showing {len(display)} of {len(rows)} rows._" if len(rows) > len(display) else ""
    return "\n".join([head, sep, *body_lines]) + tail


def run_semantic_data_analytics(user_query: str) -> dict[str, Any]:
    """
    Returns a dict always including ok: bool. On success includes answer, mdx, sql, rows_preview.
    """
    bundle, semantic_dir, notes = load_or_build_semantic_bundle()
    out: dict[str, Any] = {
        "ok": False,
        "semantic_dir": str(semantic_dir),
        "notes": notes,
    }
    if not bundle or not bundle.get("semantic_model"):
        out["error"] = "No semantic_model.json available. Run auto_olap_pipeline or set DIVALTO_SEMANTIC_MODEL_DIR."
        return out

    model = bundle["semantic_model"]
    catalog = catalog_for_llm(model)
    if not catalog.get("tables"):
        out["error"] = "Semantic model contains no tables."
        return out

    cube = _runtime_cube_name()
    if _wants_sales_by_article(user_query):
        deterministic = _run_sales_by_article_analytic(user_query, cube)
        out.update(deterministic)
        out["notes"] = notes
        return out

    system = _build_system_prompt(catalog)
    try:
        raw_plan = call_ollama_json_object(
            user_query=user_query,
            system_prompt=system,
            num_predict=OLLAMA_ANALYTIC_NUM_PREDICT,
            timeout_seconds=OLLAMA_ANALYTIC_TIMEOUT_SECONDS,
            retries=1,
        )
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"Planner LLM unavailable or invalid JSON: {exc}"
        return out

    tables = index_tables(model)
    table_name = raw_plan.get("table")
    if not isinstance(table_name, str) or table_name not in tables:
        out["error"] = f"Invalid or missing table in plan: {table_name!r}"
        out["raw_plan"] = raw_plan
        return out

    try:
        plan = validate_plan(raw_plan, tables[table_name])
    except ValueError as exc:
        if _wants_sales_by_article(user_query):
            deterministic = _run_sales_by_article_analytic(user_query, cube)
            out.update(deterministic)
            out["notes"] = notes
            out["llm_fallback_reason"] = str(exc)
            return out
        out["error"] = str(exc)
        out["raw_plan"] = raw_plan
        return out

    sql, params = compile_sqlite(plan)
    mdx = compile_mdx(plan, cube)

    answer, executed_sqlite, executed_mdx_remote = _finalize_analytic_answer(
        mdx=mdx, sql=sql, sql_params=params, cube=cube
    )
    out.update(
        {
            "ok": True,
            "plan": plan,
            "sql": sql,
            "sql_params": params,
            "mdx": mdx,
            "cube": cube,
            "executed_sqlite": executed_sqlite,
            "executed_mdx_remote": executed_mdx_remote,
            "answer": answer,
        }
    )
    return out
