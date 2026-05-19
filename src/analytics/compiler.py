"""
analytic_compiler.py
====================
Validate LLM analytic plans against the semantic catalog and compile
safe read-only SQLite SQL plus MDX aligned with auto_olap naming.
"""

from __future__ import annotations

import re
from typing import Any

_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_AGG = frozenset({"sum", "avg"})
_ALLOWED_OPS = frozenset({"=", "!=", "<", ">", "<=", ">=", "like", "in"})
_ALLOWED_GRAINS = frozenset({"day", "month", "year"})


def quote_ident(name: str) -> str:
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"Invalid identifier: {name!r}")
    return f'"{name}"'


def measure_mdx_name(column: str, aggregation: str) -> str:
    agg = aggregation.lower()
    return f"{column}_{agg}"


def validate_plan(raw: dict[str, Any], table_meta: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Plan must be a JSON object.")

    table = raw.get("table")
    if not isinstance(table, str) or table != table_meta.get("table"):
        raise ValueError("Plan table must match the selected semantic table.")

    measures_in = raw.get("measures")
    if not isinstance(measures_in, list) or not measures_in:
        raise ValueError("Plan must include a non-empty measures array.")

    allowed_measures = {
        (m["name"], str(m.get("aggregation", "sum")).lower())
        for m in (table_meta.get("measures") or [])
        if isinstance(m, dict) and isinstance(m.get("name"), str)
    }
    measures: list[dict[str, str]] = []
    for item in measures_in:
        if not isinstance(item, dict):
            continue
        col = item.get("name") or item.get("column")
        agg = str(item.get("aggregation", "sum")).lower()
        if not isinstance(col, str):
            continue
        if (col, agg) not in allowed_measures:
            raise ValueError(f"Measure not allowed for this table: {col!r} with aggregation {agg!r}")
        if agg not in _ALLOWED_AGG:
            raise ValueError(f"Unsupported aggregation: {agg!r}")
        measures.append({"name": col, "aggregation": agg})

    if not measures:
        raise ValueError("No valid measures after validation.")

    dims_in = raw.get("dimensions")
    dimensions: list[str] = []
    dim_kinds: dict[str, str] = {}
    if dims_in is not None:
        if not isinstance(dims_in, list):
            raise ValueError("dimensions must be an array of strings.")
        allowed_dims = {
            d["name"]: str(d.get("kind", "attribute"))
            for d in (table_meta.get("dimensions") or [])
            if isinstance(d, dict) and isinstance(d.get("name"), str)
        }
        for d in dims_in:
            if not isinstance(d, str) or d not in allowed_dims:
                raise ValueError(f"Dimension not allowed for this table: {d!r}")
            dimensions.append(d)
            dim_kinds[d] = allowed_dims[d]

    filters_out: list[dict[str, Any]] = []
    filters_in = raw.get("filters") or []
    if filters_in is not None and not isinstance(filters_in, list):
        raise ValueError("filters must be an array.")
    all_columns = {m["name"] for m in table_meta.get("measures", []) if isinstance(m, dict)} | set(dimensions)
    for f in filters_in or []:
        if not isinstance(f, dict):
            continue
        col = f.get("column")
        op = str(f.get("op", "=")).lower()
        if not isinstance(col, str) or col not in all_columns:
            raise ValueError(f"Filter column not in table schema: {col!r}")
        if op not in _ALLOWED_OPS:
            raise ValueError(f"Unsupported filter op: {op!r}")
        val = f.get("value")
        if op == "in":
            if not isinstance(val, list) or not val:
                raise ValueError("Filter op 'in' requires a non-empty value array.")
            for v in val:
                if not isinstance(v, (str, int, float)):
                    raise ValueError("Filter 'in' values must be string or number.")
            filters_out.append({"column": col, "op": op, "values": val})
        else:
            if val is None:
                raise ValueError("Filter value required.")
            if not isinstance(val, (str, int, float)):
                raise ValueError("Filter value must be string or number.")
            filters_out.append({"column": col, "op": op, "value": val})

    order = str(raw.get("order", "")).lower()
    if order not in {"", "asc", "desc"}:
        raise ValueError("order must be asc, desc, or omitted.")

    limit_raw = raw.get("limit")
    limit: int | None = None
    if limit_raw is not None:
        if not isinstance(limit_raw, (int, float)):
            raise ValueError("limit must be a number.")
        limit = max(1, min(int(limit_raw), 10_000))

    date_grain = str(raw.get("date_grain", "month")).lower()
    if date_grain not in _ALLOWED_GRAINS:
        date_grain = "month"

    return {
        "table": table,
        "measures": measures,
        "dimensions": dimensions,
        "dimension_kinds": dim_kinds,
        "filters": filters_out,
        "order": order or None,
        "limit": limit,
        "date_grain": date_grain,
    }


def _dimension_select_expr(table: str, col: str, kind: str, date_grain: str) -> str:
    qc = quote_ident(col)
    qt = quote_ident(table)
    if kind == "date":
        fmt = {"day": "%Y-%m-%d", "month": "%Y-%m", "year": "%Y"}.get(date_grain, "%Y-%m")
        return f"strftime('{fmt}', {qt}.{qc}) AS {quote_ident(col + '_bucket')}"
    return f"{qt}.{qc} AS {quote_ident(col)}"


def _dimension_group_expr(table: str, col: str, kind: str, date_grain: str) -> str:
    qc = quote_ident(col)
    qt = quote_ident(table)
    if kind == "date":
        fmt = {"day": "%Y-%m-%d", "month": "%Y-%m", "year": "%Y"}.get(date_grain, "%Y-%m")
        return f"strftime('{fmt}', {qt}.{qc})"
    return f"{qt}.{qc}"


def compile_sqlite(plan: dict[str, Any]) -> tuple[str, list[Any]]:
    t = plan["table"]
    qt = quote_ident(t)
    select_parts: list[str] = []
    group_parts: list[str] = []
    for d in plan["dimensions"]:
        kind = plan["dimension_kinds"].get(d, "attribute")
        select_parts.append(_dimension_select_expr(t, d, kind, plan["date_grain"]))
        group_parts.append(_dimension_group_expr(t, d, kind, plan["date_grain"]))

    agg_select: list[str] = []
    for m in plan["measures"]:
        col = quote_ident(m["name"])
        agg = m["aggregation"].upper()
        if agg == "SUM":
            agg_select.append(f"ROUND(COALESCE(SUM({qt}.{col}), 0), 4) AS {quote_ident(m['name'] + '_' + m['aggregation'])}")
        else:
            agg_select.append(f"ROUND(COALESCE(AVG({qt}.{col}), 0), 4) AS {quote_ident(m['name'] + '_' + m['aggregation'])}")

    select_parts.extend(agg_select)
    params: list[Any] = []
    where_clauses: list[str] = []
    for f in plan["filters"]:
        col = quote_ident(f["column"])
        op = f["op"].upper()
        if op == "IN":
            placeholders = ", ".join("?" * len(f["values"]))
            where_clauses.append(f"{qt}.{col} IN ({placeholders})")
            params.extend(f["values"])
        elif op == "LIKE":
            where_clauses.append(f"{qt}.{col} LIKE ?")
            params.append(str(f["value"]))
        else:
            where_clauses.append(f"{qt}.{col} {f['op']} ?")
            params.append(f["value"])

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    group_sql = f"GROUP BY {', '.join(group_parts)}" if group_parts else ""

    order_sql = ""
    if plan["order"] and agg_select:
        first_alias = plan["measures"][0]["name"] + "_" + plan["measures"][0]["aggregation"]
        order_sql = f"ORDER BY {quote_ident(first_alias)} {plan['order'].upper()}"

    limit_sql = f"LIMIT {plan['limit']}" if plan.get("limit") else ""

    sql = (
        f"SELECT {', '.join(select_parts)} FROM {qt} {where_sql} {group_sql} {order_sql} {limit_sql}"
    ).strip()
    return sql, params


def compile_mdx(plan: dict[str, Any], cube_name: str) -> str:
    table = plan["table"]
    mset = ", ".join(
        f"[Measures].[{measure_mdx_name(m['name'], m['aggregation'])}]" for m in plan["measures"]
    )
    dims = plan["dimensions"]
    if not dims:
        return f"SELECT {{ {mset} }} ON COLUMNS FROM [{cube_name}]"

    if len(dims) == 1:
        row_axis = f"NON EMPTY [{table}].[{dims[0]}].MEMBERS"
    else:
        cross = " * ".join(f"[{table}].[{d}].MEMBERS" for d in dims)
        row_axis = f"NON EMPTY {{ {cross} }}"

    return f"SELECT {{ {mset} }} ON COLUMNS, {row_axis} ON ROWS FROM [{cube_name}]"
