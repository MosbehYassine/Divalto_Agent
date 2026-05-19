"""
SQLite backend adapter used to simulate ERP webservice responses.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


def _normalize_ref(value: str) -> str:
    return (value or "").strip().lower()


def _yyyymmdd_to_iso(date_value: str) -> str:
    if not date_value:
        return ""
    value = str(date_value).strip()
    if len(value) == 8 and value.isdigit():
        return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
    return value


def _resolve_customer_filter(customer: str) -> tuple[str, tuple[Any, ...]]:
    normalized = (customer or "").strip()
    if not normalized:
        return "", ()
    # Expected ERP style "CLI-001" -> filter by numeric id.
    if normalized.upper().startswith("CLI-"):
        digits = normalized.split("-", 1)[-1]
        if digits.isdigit():
            return "AND f.id_client = ?", (int(digits),)
    # Fallback: match by exact name or email when provided.
    return "AND (c.nom = ? OR c.email = ?)", (normalized, normalized)


def _get_connection(db_path: str | None) -> sqlite3.Connection:
    path_value = db_path or "magasin_mock.db"
    path_obj = Path(path_value)
    if not path_obj.is_absolute():
        # resolve relative to current working directory where process is launched
        path_obj = (Path.cwd() / path_obj).resolve()
    if not path_obj.exists():
        raise FileNotFoundError(f"SQLite mock database not found: {path_obj}")
    conn = sqlite3.connect(str(path_obj))
    conn.row_factory = sqlite3.Row
    return conn


def execute_action(action: str, payload: dict[str, Any], db_path: str | None = None) -> dict[str, Any]:
    with _get_connection(db_path) as conn:
        if action == "interroger_stock":
            return _interroger_stock(conn, payload)
        if action == "article_plus_vendu":
            return _article_plus_vendu(conn, payload)
        if action == "classement_ventes":
            return _classement_ventes(conn, payload)
        if action == "classement_clients":
            return _classement_clients(conn, payload)
        if action == "consulter_ventes":
            return _consulter_ventes(conn, payload)
        if action == "consulter_facturation":
            return _consulter_facturation(conn, payload)
        if action == "consulter_articles":
            return _consulter_articles(conn, payload)
        if action == "consulter_clients":
            return _consulter_clients(conn, payload)
        if action == "consulter_stocks":
            return _consulter_stocks(conn, payload)
        if action == "consulter_indicateurs_analytiques":
            return _consulter_indicateurs_analytiques(conn, payload)
        if action == "integrer_piece":
            return _integrer_piece(conn, payload)
        raise ValueError(f"Unsupported action for sqlite backend: {action}")


def _interroger_stock(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    reference = payload.get("reference", "")
    warehouse = payload.get("warehouse", "*")
    ref_norm = _normalize_ref(reference)

    row = conn.execute(
        """
        SELECT a.id, a.designation, s.quantite
        FROM articles a
        JOIN stocks s ON s.id_article = a.id
        WHERE lower(a.designation) = ?
        """,
        (ref_norm,),
    ).fetchone()

    if row is None and reference.isdigit():
        row = conn.execute(
            """
            SELECT a.id, a.designation, s.quantite
            FROM articles a
            JOIN stocks s ON s.id_article = a.id
            WHERE a.id = ?
            """,
            (int(reference),),
        ).fetchone()

    if row is None:
        return {"reference": reference, "warehouse": warehouse, "quantity": 0}
    return {"reference": row["designation"], "warehouse": warehouse, "quantity": int(row["quantite"])}


def _classement_ventes(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    start_iso = _yyyymmdd_to_iso(payload.get("startDate", "19000101"))
    end_iso = _yyyymmdd_to_iso(payload.get("endDate", "99991231"))
    raw_limit = int(payload.get("limit") or 5)
    safe_limit = max(1, min(raw_limit, 50))
    order = str(payload.get("order") or "desc").strip().lower()
    order_sql = "ASC" if order == "asc" else "DESC"
    normalized_order = "asc" if order == "asc" else "desc"
    customer_filter, customer_params = _resolve_customer_filter(payload.get("customer", ""))
    rows = conn.execute(
        f"""
        SELECT
            a.designation AS reference,
            SUM(v.quantite) AS quantite,
            ROUND(SUM(v.quantite * v.prix_vente_unitaire), 2) AS ca
        FROM ventes v
        JOIN factures f ON f.id = v.id_facture
        JOIN articles a ON a.id = v.id_article
        JOIN clients c ON c.id = f.id_client
        WHERE f.date_facture BETWEEN ? AND ?
        {customer_filter}
        GROUP BY a.id
        ORDER BY quantite {order_sql}
        LIMIT ?
        """,
        (start_iso, end_iso, *customer_params, safe_limit),
    ).fetchall()
    items: list[dict[str, Any]] = []
    for idx, r in enumerate(rows, start=1):
        items.append(
            {
                "rank": idx,
                "reference": str(r["reference"] or ""),
                "quantite": int(r["quantite"] or 0),
                "ca": str(r["ca"] or "0.00"),
            }
        )
    leader_reference = ""
    if items:
        leader_reference = str(items[0]["reference"])
    return {
        "items": items,
        "leaderReference": leader_reference,
        "limit": safe_limit,
        "order": normalized_order,
        "startDate": str(payload.get("startDate") or ""),
        "endDate": str(payload.get("endDate") or ""),
    }


def _classement_clients(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    start_iso = _yyyymmdd_to_iso(payload.get("startDate", "19000101"))
    end_iso = _yyyymmdd_to_iso(payload.get("endDate", "99991231"))
    raw_limit = int(payload.get("limit") or 5)
    safe_limit = max(1, min(raw_limit, 50))
    order = str(payload.get("order") or "desc").strip().lower()
    order_sql = "ASC" if order == "asc" else "DESC"
    sort_by = str(payload.get("sortBy") or "quantite").strip().lower()
    sort_col = "ca" if sort_by == "ca" else "quantite"
    rows = conn.execute(
        f"""
        SELECT
            c.id AS client_id,
            c.nom AS nom,
            COALESCE(SUM(v.quantite), 0) AS quantite,
            ROUND(COALESCE(SUM(v.quantite * v.prix_vente_unitaire), 0), 2) AS ca,
            COUNT(DISTINCT f.id) AS nb_factures
        FROM ventes v
        JOIN factures f ON f.id = v.id_facture
        JOIN clients c ON c.id = f.id_client
        WHERE f.date_facture BETWEEN ? AND ?
        GROUP BY c.id
        HAVING quantite > 0 OR ca > 0
        ORDER BY {sort_col} {order_sql}
        LIMIT ?
        """,
        (start_iso, end_iso, safe_limit),
    ).fetchall()
    items: list[dict[str, Any]] = []
    for idx, r in enumerate(rows, start=1):
        items.append(
            {
                "rank": idx,
                "clientId": int(r["client_id"]),
                "nom": str(r["nom"] or ""),
                "quantite": int(r["quantite"] or 0),
                "ca": str(r["ca"] or "0.00"),
                "nbFactures": int(r["nb_factures"] or 0),
            }
        )
    leader = items[0] if items else {}
    return {
        "items": items,
        "leaderNom": str(leader.get("nom") or ""),
        "leaderClientId": leader.get("clientId"),
        "limit": safe_limit,
        "order": "asc" if order == "asc" else "desc",
        "sortBy": sort_col,
        "startDate": str(payload.get("startDate") or ""),
        "endDate": str(payload.get("endDate") or ""),
    }


def _article_plus_vendu(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    start_iso = _yyyymmdd_to_iso(payload.get("startDate", "19000101"))
    end_iso = _yyyymmdd_to_iso(payload.get("endDate", "99991231"))
    customer_filter, customer_params = _resolve_customer_filter(payload.get("customer", ""))

    row = conn.execute(
        f"""
        SELECT
            a.designation AS reference,
            SUM(v.quantite) AS quantite,
            ROUND(SUM(v.quantite * v.prix_vente_unitaire), 2) AS ca
        FROM ventes v
        JOIN factures f ON f.id = v.id_facture
        JOIN articles a ON a.id = v.id_article
        JOIN clients c ON c.id = f.id_client
        WHERE f.date_facture BETWEEN ? AND ?
        {customer_filter}
        GROUP BY a.id
        ORDER BY quantite DESC
        LIMIT 1
        """,
        (start_iso, end_iso, *customer_params),
    ).fetchone()

    if row is None:
        return {"reference": "", "quantite": 0, "ca": "0.00"}
    return {"reference": row["reference"], "quantite": int(row["quantite"] or 0), "ca": str(row["ca"] or "0.00")}


def _consulter_ventes(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    start_iso = _yyyymmdd_to_iso(payload.get("startDate", "19000101"))
    end_iso = _yyyymmdd_to_iso(payload.get("endDate", "99991231"))
    customer_filter, customer_params = _resolve_customer_filter(payload.get("customer", ""))
    row = conn.execute(
        f"""
        SELECT ROUND(COALESCE(SUM(v.quantite * v.prix_vente_unitaire), 0), 2) AS total_ventes
        FROM ventes v
        JOIN factures f ON f.id = v.id_facture
        JOIN clients c ON c.id = f.id_client
        WHERE f.date_facture BETWEEN ? AND ?
        {customer_filter}
        """,
        (start_iso, end_iso, *customer_params),
    ).fetchone()
    total = float(row["total_ventes"] or 0.0)
    return {"totalVentes": round(total, 2)}


def _consulter_facturation(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    start_iso = _yyyymmdd_to_iso(payload.get("startDate", "19000101"))
    end_iso = _yyyymmdd_to_iso(payload.get("endDate", "99991231"))
    customer_filter, customer_params = _resolve_customer_filter(payload.get("customer", ""))
    row = conn.execute(
        f"""
        SELECT
            COUNT(DISTINCT f.id) AS nb_factures,
            ROUND(COALESCE(SUM(v.quantite * v.prix_vente_unitaire), 0), 2) AS montant_total
        FROM factures f
        LEFT JOIN ventes v ON v.id_facture = f.id
        JOIN clients c ON c.id = f.id_client
        WHERE f.date_facture BETWEEN ? AND ?
        {customer_filter}
        """,
        (start_iso, end_iso, *customer_params),
    ).fetchone()
    return {
        "nbFactures": int(row["nb_factures"] or 0),
        "montantTotal": float(row["montant_total"] or 0.0),
        "status": payload.get("status", "all"),
    }


def _consulter_articles(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    ref = (payload.get("reference") or "").strip()
    limit = int(payload.get("limit", 50))
    query = """
        SELECT id, designation, prix_unitaire
        FROM articles
        WHERE (? = '' OR lower(designation) LIKE '%' || lower(?) || '%')
        ORDER BY designation ASC
        LIMIT ?
    """
    rows = conn.execute(query, (ref, ref, limit)).fetchall()
    return {
        "count": len(rows),
        "articles": [
            {"id": int(r["id"]), "reference": r["designation"], "prix_unitaire": float(r["prix_unitaire"])}
            for r in rows
        ],
    }


def _consulter_clients(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    customer = (payload.get("customer") or "").strip()
    region = (payload.get("region") or "").strip()
    aggregate = str(payload.get("aggregate") or "").strip().lower()
    if aggregate == "count":
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM clients
            WHERE (? = '' OR lower(nom) LIKE '%' || lower(?) || '%' OR lower(email) LIKE '%' || lower(?) || '%')
              AND (? = '' OR lower(ville) LIKE '%' || lower(?) || '%')
            """,
            (customer, customer, customer, region, region),
        ).fetchone()
        n = int(row["n"] if row is not None else 0)
        return {"aggregate": "count", "totalClients": n, "count": n, "clients": []}

    limit = int(payload.get("limit", 50))
    rows = conn.execute(
        """
        SELECT id, nom, email, ville
        FROM clients
        WHERE (? = '' OR lower(nom) LIKE '%' || lower(?) || '%' OR lower(email) LIKE '%' || lower(?) || '%')
          AND (? = '' OR lower(ville) LIKE '%' || lower(?) || '%')
        ORDER BY nom ASC
        LIMIT ?
        """,
        (customer, customer, customer, region, region, limit),
    ).fetchall()
    return {
        "count": len(rows),
        "clients": [
            {"id": int(r["id"]), "nom": r["nom"], "email": r["email"], "ville": r["ville"]}
            for r in rows
        ],
    }


def _consulter_stocks(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    ref = (payload.get("reference") or "").strip()
    limit = int(payload.get("limit", 100))
    order = str(payload.get("order", "asc")).strip().lower()
    sort_dir = "DESC" if order == "desc" else "ASC"
    rows = conn.execute(
        f"""
        SELECT a.designation AS reference, s.quantite
        FROM stocks s
        JOIN articles a ON a.id = s.id_article
        WHERE (? = '' OR lower(a.designation) LIKE '%' || lower(?) || '%')
        ORDER BY s.quantite {sort_dir}
        LIMIT ?
        """,
        (ref, ref, limit),
    ).fetchall()
    return {
        "count": len(rows),
        "order": order,
        "stocks": [{"reference": r["reference"], "quantity": int(r["quantite"])} for r in rows],
    }


def _consulter_indicateurs_analytiques(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    metric = (payload.get("metric") or "sales").strip().lower()
    start_iso = _yyyymmdd_to_iso(payload.get("startDate", "19000101"))
    end_iso = _yyyymmdd_to_iso(payload.get("endDate", "99991231"))
    group_by = (payload.get("groupBy") or "month").strip().lower()
    if metric == "quantity":
        value_expr = "SUM(v.quantite)"
    else:
        value_expr = "SUM(v.quantite * v.prix_vente_unitaire)"

    if group_by in {"ville", "city"}:
        rows = conn.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(c.ville), ''), 'Inconnue') AS bucket,
                   ROUND(COALESCE({value_expr}, 0), 2) AS value
            FROM factures f
            JOIN ventes v ON v.id_facture = f.id
            JOIN clients c ON c.id = f.id_client
            WHERE f.date_facture BETWEEN ? AND ?
            GROUP BY bucket
            ORDER BY value DESC
            """,
            (start_iso, end_iso),
        ).fetchall()
    elif group_by in {"client", "clients", "nom"}:
        min_value = payload.get("minValue")
        try:
            min_ca = float(min_value) if min_value is not None else None
        except (TypeError, ValueError):
            min_ca = None
        raw_limit = int(payload.get("limit") or (200 if min_ca is not None else 50))
        safe_limit = max(1, min(raw_limit, 500))
        having_sql = ""
        params: list[Any] = [start_iso, end_iso]
        if min_ca is not None:
            having_sql = f" HAVING ROUND(COALESCE({value_expr}, 0), 2) > ?"
            params.append(min_ca)
        params.append(safe_limit)
        rows = conn.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(c.nom), ''), 'Inconnu') AS bucket,
                   ROUND(COALESCE({value_expr}, 0), 2) AS value
            FROM factures f
            JOIN ventes v ON v.id_facture = f.id
            JOIN clients c ON c.id = f.id_client
            WHERE f.date_facture BETWEEN ? AND ?
            GROUP BY c.id
            {having_sql}
            ORDER BY value DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
    elif group_by in {"region", "regions"}:
        rows = conn.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(c.ville), ''), 'Inconnue') AS bucket,
                   ROUND(COALESCE({value_expr}, 0), 2) AS value
            FROM factures f
            JOIN ventes v ON v.id_facture = f.id
            JOIN clients c ON c.id = f.id_client
            WHERE f.date_facture BETWEEN ? AND ?
            GROUP BY bucket
            ORDER BY value DESC
            """,
            (start_iso, end_iso),
        ).fetchall()
        group_by = "region"
    elif group_by in {"article", "produit", "product"}:
        rows = conn.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(a.designation), ''), 'Inconnu') AS bucket,
                   ROUND(COALESCE({value_expr}, 0), 2) AS value
            FROM factures f
            JOIN ventes v ON v.id_facture = f.id
            JOIN articles a ON a.id = v.id_article
            WHERE f.date_facture BETWEEN ? AND ?
            GROUP BY a.id
            ORDER BY value DESC
            LIMIT 50
            """,
            (start_iso, end_iso),
        ).fetchall()
        group_by = "article"
    else:
        strftime_pattern = "%Y-%m" if group_by == "month" else "%Y-%m-%d"
        rows = conn.execute(
            f"""
            SELECT strftime('{strftime_pattern}', f.date_facture) AS bucket,
                   ROUND(COALESCE({value_expr}, 0), 2) AS value
            FROM factures f
            LEFT JOIN ventes v ON v.id_facture = f.id
            WHERE f.date_facture BETWEEN ? AND ?
            GROUP BY bucket
            ORDER BY bucket ASC
            """,
            (start_iso, end_iso),
        ).fetchall()

    result: dict[str, Any] = {
        "metric": metric,
        "groupBy": group_by,
        "series": [{"bucket": r["bucket"], "value": float(r["value"])} for r in rows if r["bucket"] is not None],
    }
    if payload.get("minValue") is not None:
        try:
            result["minValue"] = float(payload["minValue"])
        except (TypeError, ValueError):
            pass
    return result


def _integrer_piece(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    customer = (payload.get("customer") or "").strip()
    reference = (payload.get("reference") or "").strip()
    quantite = int(payload.get("quantite") or 1)
    customer_id = 1
    if customer.upper().startswith("CLI-") and customer.split("-", 1)[-1].isdigit():
        customer_id = int(customer.split("-", 1)[-1])
    # Keep id in valid range.
    max_client = conn.execute("SELECT COALESCE(MAX(id), 1) AS max_id FROM clients").fetchone()["max_id"]
    customer_id = max(1, min(customer_id, int(max_client)))

    today = datetime.now().strftime("%Y-%m-%d")
    cur = conn.execute("INSERT INTO factures (id_client, date_facture) VALUES (?, ?)", (customer_id, today))
    facture_id = cur.lastrowid

    article_row = None
    if reference:
        article_row = conn.execute(
            "SELECT id, prix_unitaire FROM articles WHERE lower(designation) = lower(?)",
            (reference,),
        ).fetchone()
    if article_row is None:
        article_row = conn.execute("SELECT id, prix_unitaire FROM articles ORDER BY id ASC LIMIT 1").fetchone()

    conn.execute(
        "INSERT INTO ventes (id_facture, id_article, quantite, prix_vente_unitaire) VALUES (?, ?, ?, ?)",
        (facture_id, int(article_row["id"]), quantite, float(article_row["prix_unitaire"])),
    )
    conn.commit()
    return {"pieceId": f"MOCK-{facture_id:06d}", "factureId": int(facture_id)}
