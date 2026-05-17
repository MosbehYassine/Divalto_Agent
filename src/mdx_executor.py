"""
mdx_executor.py
===============
Optional execution of read-only MDX against SSAS / Azure AS / Power BI XMLA
using a connection string from the environment (no credentials in code).

Requires ``pyadomd`` and Microsoft ADOMD.NET on the host when enabled.
See ``requirements-olap.txt``.
"""

from __future__ import annotations

import os
import re
from typing import Any

_FORBIDDEN_MDX = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|CREATE|ALTER|TRUNCATE|BACKUP|RESTORE|SHUTDOWN)\b",
    re.IGNORECASE,
)


def _runtime_mdx_connection_string() -> str:
    return (os.getenv("DIVALTO_MDX_CONNECTION_STRING") or "").strip()


def _runtime_mdx_execute_enabled() -> bool:
    return (os.getenv("DIVALTO_MDX_EXECUTE_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}


def _runtime_mdx_max_rows() -> int:
    try:
        return max(1, min(int(os.getenv("DIVALTO_MDX_MAX_ROWS", "500")), 50_000))
    except ValueError:
        return 500


def _runtime_mdx_timeout_seconds() -> int:
    try:
        return max(5, min(int(os.getenv("DIVALTO_MDX_TIMEOUT_SECONDS", "120")), 600))
    except ValueError:
        return 120


def mdx_looks_read_only(mdx: str) -> bool:
    text = (mdx or "").strip()
    if not text:
        return False
    if _FORBIDDEN_MDX.search(text):
        return False
    head = text.lstrip()[:20].upper()
    return head.startswith("SELECT") or head.startswith("WITH")


def should_execute_mdx_remote() -> bool:
    """True when remote MDX execution is explicitly enabled and a connection string is set."""
    return _runtime_mdx_execute_enabled() and bool(_runtime_mdx_connection_string())


def execute_mdx_cellset(
    mdx: str,
    *,
    connection_string: str | None = None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """
    Run MDX and return tabular headers + rows (tuples of scalars).

    ``connection_string`` defaults to ``DIVALTO_MDX_CONNECTION_STRING``.
    Configure a client-side timeout via ``DIVALTO_MDX_TIMEOUT_SECONDS`` when your driver stack supports it.
    """
    conn_str = (connection_string or _runtime_mdx_connection_string()).strip()
    cap = max_rows if max_rows is not None else _runtime_mdx_max_rows()
    _ = _runtime_mdx_timeout_seconds()

    if not conn_str:
        return {"ok": False, "skipped": True, "reason": "no_connection_string", "error": ""}
    if not mdx_looks_read_only(mdx):
        return {"ok": False, "skipped": False, "reason": "mdx_not_read_only", "error": "MDX rejected by read-only guard."}

    try:
        from pyadomd import Pyadomd  # type: ignore[import-untyped]
    except ImportError:
        return {
            "ok": False,
            "skipped": True,
            "reason": "pyadomd_missing",
            "error": "Install pyadomd and ADOMD.NET (see requirements-olap.txt).",
        }

    headers: list[str] = []
    rows: list[tuple[Any, ...]] = []
    try:
        conn = Pyadomd(conn_str)
        conn.open()
        try:
            cur = conn.cursor()
            cur.execute(mdx)
            desc = cur.description
            if desc:
                headers = []
                for col in desc:
                    if hasattr(col, "name"):
                        headers.append(str(col.name))
                    elif isinstance(col, tuple) and col:
                        headers.append(str(col[0]))
                    else:
                        headers.append(str(col))
            fetched: list[tuple[Any, ...]] = []
            while len(fetched) < cap:
                batch = cur.fetchmany(min(100, cap - len(fetched)))
                if not batch:
                    break
                for row in batch:
                    fetched.append(tuple(row))
            rows = fetched
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "skipped": False, "reason": "execution_error", "error": str(exc)}

    return {
        "ok": True,
        "skipped": False,
        "headers": headers,
        "rows": rows,
        "truncated": len(rows) >= cap,
        "max_rows": cap,
    }
