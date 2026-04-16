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
from settings import (
    AUTH_TIMEOUT_SECONDS,
    AUTH_TOKEN_TTL_SECONDS,
    AUTH_URL,
    CREDENTIALS,
    DOSSIER_CODE,
    HTTP_MAX_RETRIES,
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
    schema_path = Path(__file__).resolve().parent / "ws_schemas.json"
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

def format_response(action: str, erp_data: dict) -> str:
    """
    Converts the raw ERP JSON response into a readable business answer.
    Add a new elif block for each new webservice you onboard.
    """

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

    elif action == "integrer_piece":
        piece_id = erp_data.get("pieceId", erp_data.get("id", "?"))
        return f"La pièce a été créée avec succès (ID : {piece_id})."

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

    answer = format_response(action, erp_response)
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
