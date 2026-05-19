"""
Divalto Agent — Backend Script
Phase 2: Interrogation Stock (pilot webservice)

Pipeline:
  LLM JSON output
      → validate_payload()
      → get_token()
      → call_webservice()
      → format_response()

Extend by adding new entries to WS_SCHEMAS for each new webservice.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional
import requests

from phase4.prefunctions import focus_terms_for_answer, normalize_text

from core.settings import (
    AUTH_TIMEOUT_SECONDS,
    AUTH_TOKEN_TTL_SECONDS,
    AUTH_URL,
    CREDENTIALS,
    DOSSIER_CODE,
    HTTP_MAX_RETRIES,
    SQLITE_MOCK_DB_PATH,
    USE_SQLITE_MOCK,
    WS_TIMEOUT_SECONDS,
    WS_URL,
)


logger = logging.getLogger("divalto_agent")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

SESSION = requests.Session()
_TOKEN_CACHE: dict[str, Any] = {"token": None, "expires_at": 0.0}


def _build_error(code: str, message: str, retryable: bool = False, details: dict | None = None) -> dict:
    return {
        "code": code,
        "message": message,
        "retryable": retryable,
        "details": details or {},
    }


def _request_with_retries(method: str, url: str, **kwargs) -> requests.Response:
    """
    Execute HTTP requests with simple retry policy for transient failures.
    """
    last_exc = None
    for attempt in range(1, HTTP_MAX_RETRIES + 1):
        try:
            return SESSION.request(method=method, url=url, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_exc = exc
            if attempt == HTTP_MAX_RETRIES:
                raise
            sleep_s = min(0.5 * (2 ** (attempt - 1)), 2.0)
            logger.warning(
                "[HTTP] transient error on %s %s (attempt %s/%s): %s. Retrying in %.1fs",
                method,
                url,
                attempt,
                HTTP_MAX_RETRIES,
                exc,
                sleep_s,
            )
            time.sleep(sleep_s)
    raise last_exc  # pragma: no cover


# ─────────────────────────────────────────────
# WS SCHEMAS  (from champs_web_service.docx)
#
# Each entry defines:
#   required  → must be present, block if missing
#   optional  → use default value if absent
# ─────────────────────────────────────────────

def _load_ws_schemas() -> dict:
    """
    Load action schemas from JSON so adding new business actions
    does not require Python code edits.
    """
    schema_path = Path(__file__).resolve().parent.parent / "config" / "ws_schemas.json"
    try:
        with schema_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("Schema file must contain a JSON object")
        return data
    except Exception as exc:
        raise RuntimeError(f"Failed to load WS schemas from {schema_path}: {exc}") from exc


WS_SCHEMAS = _load_ws_schemas()


# ─────────────────────────────────────────────
# STEP 1 — VALIDATE & COMPLETE PAYLOAD
# ─────────────────────────────────────────────

def validate_payload(llm_json: dict) -> dict:
    """
    Takes the raw JSON output from the LLM.
    Checks required fields, applies defaults for optional fields.

    Returns:
        { "ok": True,  "data": { ...completed payload... } }
        { "ok": False, "missing": ["field1", ...] }
    """
    action = llm_json.get("action")

    if action not in WS_SCHEMAS:
        return {
            "ok":    False,
            "error": f"Unknown action '{action}'. "
                     f"Available: {list(WS_SCHEMAS.keys())}"
        }

    schema   = WS_SCHEMAS[action]
    payload  = dict(llm_json)           # copy so we don't mutate the original
    missing  = []

    # 1. Check all required fields are present and non-empty
    for field in schema["required"]:
        if not payload.get(field):
            missing.append(field)

    if missing:
        return {
            "ok":      False,
            "missing": missing,
            "message": f"Missing required field(s) for '{action}': "
                       f"{', '.join(missing)}. Please provide them."
        }

    # 2. Apply defaults for any optional field not provided by the LLM
    for field, default in schema["optional"].items():
        if not payload.get(field):
            payload[field] = default

    return {"ok": True, "data": payload}


# ─────────────────────────────────────────────
# STEP 2 — GET AUTH TOKEN
# ─────────────────────────────────────────────

def get_token_details(force_refresh: bool = False) -> dict:
    """
    POSTs credentials to the auth endpoint.
    Returns a standardized result dict.
    """
    if USE_SQLITE_MOCK:
        return {"ok": True, "token": "sqlite-mock-token", "cached": True}

    now = time.time()
    cached_token = _TOKEN_CACHE.get("token")
    if cached_token and not force_refresh and now < _TOKEN_CACHE.get("expires_at", 0):
        return {"ok": True, "token": cached_token, "cached": True}

    try:
        response = _request_with_retries(
            "POST", AUTH_URL, json=CREDENTIALS, timeout=AUTH_TIMEOUT_SECONDS
        )
        response.raise_for_status()

        body = response.json()
        token = body.get("token")
        if not token:
            logger.error("[Auth] response received but no 'token' field found.")
            logger.error("[Auth] Response body: %s", response.text)
            return {
                "ok": False,
                "error": _build_error(
                    "AUTH_MISSING_TOKEN",
                    "Auth response did not include token.",
                    retryable=False,
                    details={"response_text": response.text},
                ),
            }

        logger.info("[Auth] TOKEN obtained successfully.")
        ttl = int(body.get("expiresIn") or body.get("expires_in") or AUTH_TOKEN_TTL_SECONDS)
        _TOKEN_CACHE["token"] = token
        _TOKEN_CACHE["expires_at"] = time.time() + max(ttl - 30, 30)
        return {"ok": True, "token": token, "cached": False}

    except requests.exceptions.ConnectionError:
        logger.error("[Auth] Could not reach %s. Check BASE_URL.", AUTH_URL)
        return {
            "ok": False,
            "error": _build_error(
                "AUTH_CONNECTION_ERROR",
                f"Could not reach auth endpoint: {AUTH_URL}",
                retryable=True,
            ),
        }
    except requests.exceptions.Timeout:
        logger.error("[Auth] Request timed out.")
        return {
            "ok": False,
            "error": _build_error(
                "AUTH_TIMEOUT",
                "Auth request timed out.",
                retryable=True,
            ),
        }
    except requests.exceptions.HTTPError as e:
        logger.error("[Auth] HTTP error: %s", e)
        return {
            "ok": False,
            "error": _build_error(
                "AUTH_HTTP_ERROR",
                f"Auth HTTP error: {e}",
                retryable=False,
            ),
        }


def get_token() -> Optional[str]:
    result = get_token_details()
    if result.get("ok"):
        return result["token"]
    return None


# ─────────────────────────────────────────────
# STEP 3 — CALL THE DIVALTO WEBSERVICE
# ─────────────────────────────────────────────

def call_webservice_details(token: str, validated_data: dict) -> dict:
    """
    Builds the Divalto WS payload and POSTs it to the endpoint.
    Returns the parsed ERP response dict, or None on failure.

    Payload structure (from Guide_web_service.docx):
    {
      "action": {
        "swinfinity": "<action_name>",
        "parameters": { "dos": "998" }
      },
      "data": { ...validated fields... }
    }
    """
    action = validated_data.pop("action")   # pull action out of data

    if USE_SQLITE_MOCK:
        try:
            from core.sqlite_backend import execute_action

            data = execute_action(action, validated_data, SQLITE_MOCK_DB_PATH or None)
            logger.info("[WS-SQLITE] Action '%s' executed on sqlite backend.", action)
            return {"ok": True, "data": data}
        except Exception as exc:
            logger.error("[WS-SQLITE] backend execution failed: %s", exc)
            return {
                "ok": False,
                "error": _build_error(
                    "WS_SQLITE_BACKEND_ERROR",
                    f"SQLite backend execution failed: {exc}",
                    retryable=False,
                ),
            }

    ws_payload = {
        "action": {
            "swinfinity": action,
            "parameters": {"dos": DOSSIER_CODE}
        },
        "data": validated_data
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json"
    }

    try:
        response = _request_with_retries(
            "POST",
            WS_URL,
            json=ws_payload,
            headers=headers,
            timeout=WS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        logger.info("[WS] Call successful.")
        return {"ok": True, "data": response.json()}

    except requests.exceptions.HTTPError as e:
        logger.error("[WS] HTTP error: %s", e)
        logger.error("[WS] Response: %s", response.text)
        return {
            "ok": False,
            "error": _build_error(
                "WS_HTTP_ERROR",
                f"Webservice HTTP error: {e}",
                retryable=False,
                details={"response_text": response.text},
            ),
        }
    except requests.exceptions.ConnectionError:
        logger.error("[WS] Could not reach %s.", WS_URL)
        return {
            "ok": False,
            "error": _build_error(
                "WS_CONNECTION_ERROR",
                f"Could not reach webservice endpoint: {WS_URL}",
                retryable=True,
            ),
        }
    except requests.exceptions.Timeout:
        logger.error("[WS] Request timed out.")
        return {
            "ok": False,
            "error": _build_error(
                "WS_TIMEOUT",
                "Webservice request timed out.",
                retryable=True,
            ),
        }
    except json.JSONDecodeError:
        logger.error("[WS] Could not parse ERP response as JSON.")
        logger.error("[WS] Raw response: %s", response.text)
        return {
            "ok": False,
            "error": _build_error(
                "WS_JSON_DECODE_ERROR",
                "Could not parse ERP response as JSON.",
                retryable=False,
                details={"response_text": response.text},
            ),
        }


def call_webservice(token: str, validated_data: dict) -> Optional[dict]:
    result = call_webservice_details(token, validated_data)
    if result.get("ok"):
        return result["data"]
    return None


# ─────────────────────────────────────────────
# STEP 4 — FORMAT ERP RESPONSE → HUMAN ANSWER
# ─────────────────────────────────────────────

def _score_row_match(row: dict[str, Any], terms: list[str], field_weights: dict[str, int]) -> int:
    if not terms:
        return 0
    score = 0
    for field, weight in field_weights.items():
        val = normalize_text(str(row.get(field) or ""))
        for term in terms:
            if term and term in val:
                score += weight
    return score


def _rank_rows_by_question(rows: list[dict[str, Any]], user_query: str, field_weights: dict[str, int]) -> list[tuple[int, dict[str, Any]]]:
    terms = focus_terms_for_answer(user_query)
    scored = [(_score_row_match(r, terms, field_weights), r) for r in rows]
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def _format_one_client_row(row: dict[str, Any]) -> str:
    nom = row.get("nom") or "?"
    cid = row.get("id", "?")
    email = row.get("email") or "non renseigné"
    ville = row.get("ville") or "non renseignée"
    return (
        f"Le client « {nom} » (identifiant {cid}) — e-mail : {email}, ville : {ville}."
    )


def _format_clients_answer(erp_data: dict, user_query: str) -> str:
    clients = erp_data.get("clients") or []
    if not isinstance(clients, list) or len(clients) == 0:
        return "Aucun client ne correspond à cette recherche."

    weights = {"nom": 5, "email": 2, "ville": 1}
    ranked = _rank_rows_by_question(clients, user_query, weights)
    terms = focus_terms_for_answer(user_query)
    top_s, top_row = ranked[0]
    second_s = ranked[1][0] if len(ranked) > 1 else -1

    unique_best = len(clients) == 1 or (
        top_s > 0 and (top_s >= second_s + 2 or (second_s <= 0 and top_s >= 3))
    )
    if unique_best:
        return _format_one_client_row(top_row)

    if not terms:
        head = "\n".join(
            f"• {_format_one_client_row(r)}" for _, r in ranked[: min(5, len(ranked))]
        )
        tail_note = ""
        if len(clients) > 5:
            tail_note = f"\n({len(clients)} résultats au total — précisez un nom ou un code client.)"
        return "Voici les premiers clients correspondant à la recherche :\n" + head + tail_note

    lines = [_format_one_client_row(r) for _, r in ranked[:3]]
    body = "\n".join(f"• {line}" for line in lines)
    more = len(ranked) - 3
    suffix = f"\n({more} autre(s) correspondance(s) — précisez le nom ou le code client.)" if more > 0 else ""
    return (
        "Plusieurs clients correspondent partiellement à votre question ; les plus probables sont :\n"
        + body
        + suffix
    )


def _format_one_article_row(row: dict[str, Any]) -> str:
    ref = row.get("reference") or "?"
    aid = row.get("id", "?")
    prix = row.get("prix_unitaire")
    prix_txt = f"{prix} €" if prix is not None else "prix non renseigné"
    return f"L'article « {ref} » (identifiant {aid}) est au prix unitaire de {prix_txt}."


def _format_articles_answer(erp_data: dict, user_query: str) -> str:
    articles = erp_data.get("articles") or []
    if not isinstance(articles, list) or len(articles) == 0:
        return "Aucun article ne correspond à cette recherche."

    weights = {"reference": 6}
    ranked = _rank_rows_by_question(articles, user_query, weights)
    terms = focus_terms_for_answer(user_query)
    top_s, top_row = ranked[0]
    second_s = ranked[1][0] if len(ranked) > 1 else -1

    unique_best = len(articles) == 1 or (
        top_s > 0 and (top_s >= second_s + 2 or (second_s <= 0 and top_s >= 3))
    )
    if unique_best:
        return _format_one_article_row(top_row)

    if not terms:
        head = "\n".join(f"• {_format_one_article_row(r)}" for _, r in ranked[: min(5, len(ranked))])
        tail = ""
        if len(articles) > 5:
            tail = f"\n({len(articles)} résultats au total — précisez la désignation ou la référence.)"
        return "Voici les premiers articles trouvés :\n" + head + tail

    lines = [_format_one_article_row(r) for _, r in ranked[:3]]
    body = "\n".join(f"• {line}" for line in lines)
    more = len(ranked) - 3
    suffix = f"\n({more} autre(s) ligne(s) — précisez la référence.)" if more > 0 else ""
    return (
        "Plusieurs articles correspondent à votre recherche ; les plus pertinents semblent être :\n"
        + body
        + suffix
    )


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    def esc(cell: str) -> str:
        return str(cell).replace("|", "\\|")

    lines = [
        "| " + " | ".join(esc(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(esc(c) for c in row) + " |")
    return "\n".join(lines)


def render_client_ranking_table(items: list[dict[str, Any]]) -> str:
    headers = ["#", "Client", "Qté", "CA (€)", "Factures"]
    body: list[list[str]] = []
    ordered = sorted(items, key=lambda row: row.get("rank", 999))
    for row in ordered:
        body.append(
            [
                str(row.get("rank", "?")),
                str(row.get("nom", "?")),
                str(row.get("quantite", "?")),
                str(row.get("ca", "?")),
                str(row.get("nbFactures", "?")),
            ]
        )
    return _markdown_table(headers, body)


def render_analytic_series_table(
    series: list[dict[str, Any]],
    *,
    metric: str,
    group_by: str,
) -> str:
    dim_labels = {
        "ville": "Ville",
        "client": "Client",
        "region": "Région",
        "article": "Article",
        "month": "Mois",
        "day": "Jour",
    }
    dim_col = dim_labels.get(group_by, group_by.capitalize())
    measure_col = "Volume" if metric == "quantity" else "Chiffre d'affaires (€)"
    body: list[list[str]] = []
    for point in series:
        bucket = str(point.get("bucket", "?"))
        val = float(point.get("value") or 0.0)
        if metric == "quantity":
            body.append([bucket, f"{val:.0f}"])
        else:
            body.append([bucket, f"{val:,.2f}".replace(",", " ")])
    return _markdown_table([dim_col, measure_col], body)


def format_response(action: str, erp_data: dict, user_query: str = "") -> str:
    """
    Converts the raw ERP JSON response into a readable business answer.
    Add a new elif block for each new webservice you onboard.
    """

    user_question = user_query or ""

    if action == "interroger_stock":
        reference = erp_data.get("reference", "?")
        warehouse = erp_data.get("warehouse", "*")
        quantity  = erp_data.get("quantity",  erp_data.get("quantite", "?"))

        if warehouse == "*":
            return (f"L'article '{reference}' a {quantity} unité(s) en stock "
                    f"(tous dépôts confondus).")
        else:
            return (f"L'article '{reference}' a {quantity} unité(s) en stock "
                    f"au dépôt '{warehouse}'.")

    elif action == "article_plus_vendu":
        article  = erp_data.get("reference", "?")
        quantity = erp_data.get("quantite",  "?")
        ca       = erp_data.get("ca",        None)
        msg = f"L'article le plus vendu est '{article}' avec {quantity} unité(s) vendues."
        if ca:
            msg += f" CA généré : {ca}."
        return msg

    elif action == "classement_clients":
        items = erp_data.get("items") or []
        if not isinstance(items, list) or len(items) == 0:
            return "Aucun achat client enregistré sur la période analysée."
        top = items[0]
        nom = top.get("nom", "?")
        cid = top.get("clientId", "?")
        sort_by = str(erp_data.get("sortBy") or "quantite").lower()
        if sort_by == "ca":
            headline = (
                f"Le client avec le plus gros chiffre d'affaires est « {nom} » "
                f"(identifiant {cid}) avec {top.get('ca')} € de CA."
            )
        else:
            headline = (
                f"Le client qui achète le plus (volume) est « {nom} » "
                f"(identifiant {cid}) avec {top.get('quantite')} unité(s) achetées."
            )
        if len(items) > 1:
            return headline + "\n\nClassement clients (extrait) :\n" + render_client_ranking_table(items)
        return headline

    elif action == "classement_ventes":
        items = erp_data.get("items") or []
        if not isinstance(items, list) or len(items) == 0:
            return "Classement des ventes : aucun mouvement sur la période."
        top = items[0]
        ref = top.get("reference", "?")
        qty = top.get("quantite", "?")
        ca = top.get("ca")
        order = str(erp_data.get("order") or "desc").lower()
        suffix = ""
        if len(items) > 1:
            suffix = f" Le classement compte {len(items)} ligne(s)."
        if order == "asc":
            msg = (
                f"L'article le moins vendu est '{ref}' ({qty} unité(s))."
                + (f" CA : {ca}." if ca is not None else "")
                + suffix
            )
        else:
            msg = (
                f"En tête des ventes : '{ref}' ({qty} unité(s))."
                + (f" CA : {ca}." if ca is not None else "")
                + suffix
            )
        return msg

    elif action == "integrer_piece":
        piece_id = erp_data.get("pieceId", erp_data.get("id", "?"))
        return f"La pièce a été créée avec succès (ID : {piece_id})."

    elif action == "consulter_ventes":
        total = erp_data.get("totalVentes", 0)
        return f"Le total des ventes sur la période est de {total} €."

    elif action == "consulter_facturation":
        nb = erp_data.get("nbFactures", 0)
        montant = erp_data.get("montantTotal", 0)
        return f"Facturation: {nb} facture(s), montant total {montant} €."

    elif action == "consulter_stocks":
        items = erp_data.get("stocks") or []
        if not isinstance(items, list) or len(items) == 0:
            return "Aucun stock trouvé pour ce filtre."
        terms = focus_terms_for_answer(user_question)
        ranked = _rank_rows_by_question(items, user_question, {"reference": 4})
        pick = items[0]
        if len(items) > 1 and terms and ranked[0][0] > 0:
            pick = ranked[0][1]
        ref = pick.get("reference", "?")
        qty = pick.get("quantity", pick.get("quantite", "?"))
        order = str(erp_data.get("order") or "asc").lower()
        if len(items) == 1:
            return f"Pour « {ref} », le stock disponible est de {qty} unité(s)."
        if len(items) > 1 and terms and ranked[0][0] > 0:
            return (
                f"Pour votre recherche, la ligne la plus pertinente est « {ref} » "
                f"avec {qty} unité(s). ({len(items)} article(s) dans la liste filtrée.)"
            )
        if order == "desc":
            return f"L'article avec le stock le plus élevé est « {ref} » avec {qty} unité(s)."
        return f"L'article avec le stock le plus faible est « {ref} » avec {qty} unité(s)."

    elif action == "consulter_clients":
        if str(erp_data.get("aggregate") or "").lower() == "count":
            n = erp_data.get("totalClients")
            if n is None:
                n = erp_data.get("count", 0)
            return f"Il y a {n} client(s) correspondant aux critères demandés."
        return _format_clients_answer(erp_data, user_question)

    elif action == "consulter_articles":
        return _format_articles_answer(erp_data, user_question)

    elif action == "consulter_indicateurs_analytiques":
        series = erp_data.get("series") or []
        if not isinstance(series, list) or len(series) == 0:
            return "Aucune donnée analytique sur la période demandée."
        metric = erp_data.get("metric", "?")
        group_by = str(erp_data.get("groupBy", "?")).lower()
        total = sum(float(p.get("value") or 0.0) for p in series)
        unit = "€" if metric != "quantity" else "unité(s)"

        dim_labels = {
            "ville": "ville",
            "client": "client",
            "region": "région",
            "article": "article",
            "month": "mois",
            "day": "jour",
        }
        dim_label = dim_labels.get(group_by, group_by)

        if group_by in {"ville", "client", "region", "article"}:
            measure_label = "Chiffre d'affaires" if metric != "quantity" else "Volume vendu"
            min_val = erp_data.get("minValue")
            if min_val is not None and group_by == "client":
                headline = (
                    f"Clients avec un {measure_label.lower()} supérieur à "
                    f"{float(min_val):,.2f} € ({len(series)} client(s)) :"
                ).replace(",", " ")
            else:
                headline = (
                    f"{measure_label} par {dim_label} ({len(series)} lignes), "
                    f"total {total:.2f} {unit}."
                )
            display_series = series[:50]
            table = render_analytic_series_table(
                display_series, metric=metric, group_by=group_by
            )
            extra = ""
            if len(series) > len(display_series):
                extra = f"\n\n… ({len(series) - len(display_series)} ligne(s) supplémentaire(s))."
            return f"{headline}\n\n{table}{extra}"

        preview = ", ".join(f"{p.get('bucket')} -> {p.get('value')}" for p in series[:8])
        ellipsis = " …" if len(series) > 8 else ""
        return (
            f"Indicateur « {metric} » ({group_by}) sur {len(series)} période(s), "
            f"cumul environ {total:.2f}. Détail : {preview}{ellipsis}"
        )

    else:
        # Fallback: dump the raw response
        return f"Réponse ERP reçue : {json.dumps(erp_data, ensure_ascii=False)}"


# ─────────────────────────────────────────────
# MAIN ENTRY POINT — run_agent()
# ─────────────────────────────────────────────

def run_agent(llm_json: dict) -> str:
    """
    Full pipeline:
      llm_json → validate → get_token → call_ws → format_response

    Args:
        llm_json: the structured JSON produced by the LLM, e.g.:
            {
                "action":    "interroger_stock",
                "reference": "ALB0001",
                "warehouse": ""
            }

    Returns:
        A human-readable string answer, or an error/clarification message.
    """

    logger.info("--- Divalto Agent ---")
    logger.info("[Input] %s", llm_json)

    result = run_agent_structured(llm_json)
    if result["ok"]:
        return result["answer"]
    error = result["error"]
    if error["code"] == "VALIDATION_MISSING_FIELDS":
        return error["message"]
    if error["code"] == "VALIDATION_ERROR":
        return f"Erreur de validation : {error['message']}"
    if error["code"].startswith("AUTH_"):
        return "Erreur : impossible d'obtenir le token d'authentification. Vérifiez les credentials."
    if error["code"].startswith("WS_"):
        return "Erreur : l'appel au webservice Divalto a échoué. Vérifiez l'URL et réessayez."
    return f"Erreur : {error['message']}"


def run_agent_structured(llm_json: dict) -> dict:
    """
    Structured variant of run_agent with normalized error payload.
    """
    logger.info("--- Divalto Agent ---")
    logger.info("[Input] %s", llm_json)

    validation = validate_payload(llm_json)
    if not validation["ok"]:
        if "missing" in validation:
            return {
                "ok": False,
                "error": _build_error(
                    "VALIDATION_MISSING_FIELDS",
                    validation["message"],
                    retryable=False,
                    details={"missing": validation["missing"]},
                ),
            }
        return {
            "ok": False,
            "error": _build_error(
                "VALIDATION_ERROR",
                validation.get("error", "Unknown validation error."),
                retryable=False,
            ),
        }

    validated = validation["data"]
    action = validated.get("action")
    logger.info("[Validate] OK - action='%s', payload=%s", action, validated)

    auth_result = get_token_details()
    if not auth_result["ok"]:
        return {"ok": False, "error": auth_result["error"]}
    token = auth_result["token"]

    ws_result = call_webservice_details(token, dict(validated))
    if not ws_result["ok"]:
        return {"ok": False, "error": ws_result["error"]}
    erp_response = ws_result["data"]
    logger.info("[ERP Response] %s", erp_response)

    answer = format_response(action, erp_response, user_query="")
    logger.info("[Answer] %s", answer)
    return {"ok": True, "answer": answer, "raw": erp_response}


# ─────────────────────────────────────────────
# QUICK TEST  (run this file directly to test)
# ─────────────────────────────────────────────

if __name__ == "__main__":

    # Simulate the LLM output for Interrogation Stock
    test_cases = [

        # Normal case — warehouse provided
        {
            "action":    "interroger_stock",
            "reference": "ALB0001",
            "warehouse": "DEP01"
        },

        # Optional field missing — should default warehouse to "*"
        {
            "action":    "interroger_stock",
            "reference": "ALB0001"
        },

        # Required field missing — should block and ask user
        {
            "action":    "interroger_stock",
            "warehouse": "DEP01"
        },

        # Unknown action — should return clear error
        {
            "action": "unknown_action",
            "reference": "ALB0001"
        }
    ]

    for i, test in enumerate(test_cases, 1):
        print(f"\n{'='*50}")
        print(f"TEST CASE {i}")
        result = run_agent(test)
        print(f"\nFINAL ANSWER -> {result}")
