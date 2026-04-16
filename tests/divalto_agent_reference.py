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

import requests
import json
from typing import Optional


# ─────────────────────────────────────────────
# CONFIGURATION  (replace with real values)
# ─────────────────────────────────────────────

BASE_URL   = "https://your-divalto-server.com"   # base URL from the company
AUTH_URL   = f"{BASE_URL}/auth"
WS_URL     = f"{BASE_URL}/webservice"

CREDENTIALS = {
    "user":     "Infolib",
    "password": "LibInfo",
    "env":      "ERP221"
}


# ─────────────────────────────────────────────
# WS SCHEMAS  (from champs_web_service.docx)
#
# Each entry defines:
#   required  → must be present, block if missing
#   optional  → use default value if absent
# ─────────────────────────────────────────────

WS_SCHEMAS = {

    "interroger_stock": {
        "required": ["reference"],
        "optional": {
            "warehouse": "*"        # default = all depots
        }
    },

    "article_plus_vendu": {
        "required": [],
        "optional": {
            "startDate": "19000101",
            "endDate":   "99991231",
            "customer":  ""
        }
    },

    "integrer_piece": {
        "required": ["pieceType", "customerType", "customer"],
        "optional": {
            "reference": "",
            "quantite":  1
        }
    }
}


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

def get_token() -> Optional[str]:
    """
    POSTs credentials to the auth endpoint.
    Returns the TOKEN string, or None on failure.
    """
    try:
        response = requests.post(
            AUTH_URL,
            json=CREDENTIALS,
            timeout=10
        )
        response.raise_for_status()

        token = response.json().get("token")
        if not token:
            print("[Auth] ERROR: response received but no 'token' field found.")
            print("[Auth] Response body:", response.text)
            return None

        print("[Auth] TOKEN obtained successfully.")
        return token

    except requests.exceptions.ConnectionError:
        print(f"[Auth] ERROR: Could not reach {AUTH_URL}. Check BASE_URL.")
        return None
    except requests.exceptions.Timeout:
        print("[Auth] ERROR: Request timed out.")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"[Auth] HTTP error: {e}")
        return None


# ─────────────────────────────────────────────
# STEP 3 — CALL THE DIVALTO WEBSERVICE
# ─────────────────────────────────────────────

def call_webservice(token: str, validated_data: dict) -> Optional[dict]:
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
            "parameters": { "dos": "998" }  # dos = company/dossier code
        },
        "data": validated_data
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json"
    }

    try:
        response = requests.post(
            WS_URL,
            json=ws_payload,
            headers=headers,
            timeout=15
        )
        response.raise_for_status()

        print("[WS] Call successful.")
        return response.json()

    except requests.exceptions.HTTPError as e:
        print(f"[WS] HTTP error: {e}")
        print("[WS] Response:", response.text)
        return None
    except requests.exceptions.ConnectionError:
        print(f"[WS] ERROR: Could not reach {WS_URL}.")
        return None
    except requests.exceptions.Timeout:
        print("[WS] ERROR: Request timed out.")
        return None
    except json.JSONDecodeError:
        print("[WS] ERROR: Could not parse ERP response as JSON.")
        print("[WS] Raw response:", response.text)
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

    print("\n─── Divalto Agent ───")
    print(f"[Input] {llm_json}")

    # Step 1 — Validate
    validation = validate_payload(llm_json)
    if not validation["ok"]:
        if "missing" in validation:
            return validation["message"]   # ask user for missing fields
        return f"Erreur de validation : {validation.get('error')}"

    validated = validation["data"]
    action    = validated.get("action")
    print(f"[Validate] OK — action='{action}', payload={validated}")

    # Step 2 — Auth
    token = get_token()
    if not token:
        return "Erreur : impossible d'obtenir le token d'authentification. Vérifiez les credentials."

    # Step 3 — WS call (pop action before passing data)
    data_to_send = dict(validated)
    erp_response = call_webservice(token, data_to_send)
    if erp_response is None:
        return "Erreur : l'appel au webservice Divalto a échoué. Vérifiez l'URL et réessayez."

    print(f"[ERP Response] {erp_response}")

    # Step 4 — Format
    answer = format_response(action, erp_response)
    print(f"[Answer] {answer}")
    return answer


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
        print(f"\nFINAL ANSWER → {result}")
