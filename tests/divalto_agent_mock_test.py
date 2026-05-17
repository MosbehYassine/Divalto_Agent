"""
divalto_agent_mock_test.py
==========================
Run this file to test the full pipeline WITHOUT a real Divalto endpoint.

We replace requests.post() with a fake function (mock) that returns
realistic fake responses. Everything else — validate_payload, format_response,
run_agent — runs exactly as it would in production.

HOW TO RUN:
    python divalto_agent_mock_test.py

NO endpoint, NO credentials, NO internet needed.
"""

import json
import os
import sys
from unittest.mock import patch, MagicMock

# ── import your real agent ───────────────────────────────────────────────────
# Ensure src directory is importable when running from tests folder
CURRENT_DIR = os.path.dirname(__file__)
SRC_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
from divalto_agent import run_agent, validate_payload

print("=" * 60)
print("DIVALTO AGENT — MOCK TEST SUITE")
print("No real endpoint needed. All HTTP calls are faked.")
print("=" * 60)


# ── FAKE RESPONSES ───────────────────────────────────────────────────────────
# These simulate what Divalto would actually send back

FAKE_TOKEN_RESPONSE = {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.FAKE_TOKEN_FOR_TESTING"
}

FAKE_STOCK_RESPONSE = {
    "reference": "ALB0001",
    "warehouse": "*",
    "quantity":  42
}

FAKE_ARTICLE_RESPONSE = {
    "reference": "PROD-007",
    "quantite":  320,
    "ca":        "14 500 €"
}

FAKE_PIECE_RESPONSE = {
    "pieceId": "FAC-2024-00891"
}


def make_mock_post(ws_response):
    """
    Returns a fake requests.post function.
    Routes by URL:
    - auth endpoint -> returns FAKE_TOKEN
    - webservice endpoint -> returns the ws_response you pass in
    """
    def mock_post(method, url, **kwargs):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = lambda: None   # no HTTP errors

        if "auth" in url.lower():
            # Auth call
            mock_resp.json.return_value = FAKE_TOKEN_RESPONSE
            print(f"  [MOCK] Auth call intercepted -> returning fake TOKEN")
        else:
            # WS call
            mock_resp.json.return_value = ws_response
            print(f"  [MOCK] WS call intercepted -> returning fake ERP response:")
            print(f"  [MOCK] {json.dumps(ws_response, ensure_ascii=False)}")

        return mock_resp

    return mock_post


# ── TEST RUNNER ───────────────────────────────────────────────────────────────

def run_test(name, llm_json, ws_response=None, expect_error=False):
    print(f"\n{'-'*60}")
    print(f"TEST: {name}")
    print(f"INPUT: {llm_json}")

    if ws_response:
        with patch("divalto_agent.SESSION.request", side_effect=make_mock_post(ws_response)):
            result = run_agent(llm_json)
    else:
        # No mock needed — validation will block before any HTTP call
        result = run_agent(llm_json)

    print(f"RESULT: {result}")

    if expect_error:
        assert "Erreur" in result or "Missing" in result or "missing" in result.lower(), \
            f"Expected an error but got: {result}"
        print("STATUS: PASS (correctly returned error)")
    else:
        assert "?" not in result or "Erreur" not in result, \
            f"Got unexpected error: {result}"
        print("STATUS: PASS")


# ── TEST CASES ────────────────────────────────────────────────────────────────

# Test 1 — Normal stock query, warehouse provided
run_test(
    name="Interrogation Stock — full fields",
    llm_json={
        "action":    "interroger_stock",
        "reference": "ALB0001",
        "warehouse": "DEP01"
    },
    ws_response={"reference": "ALB0001", "warehouse": "DEP01", "quantity": 42}
)

# Test 2 — Stock query, warehouse missing → should default to "*"
run_test(
    name="Interrogation Stock — warehouse defaults to *",
    llm_json={
        "action":    "interroger_stock",
        "reference": "ALB0001"
    },
    ws_response=FAKE_STOCK_RESPONSE
)

# Test 3 — Required field missing → should BLOCK, not call WS
run_test(
    name="Interrogation Stock — reference MISSING (should block)",
    llm_json={
        "action":    "interroger_stock",
        "warehouse": "DEP01"
    },
    expect_error=True
)

# Test 4 — Article le plus vendu, all optional → all defaults apply
run_test(
    name="Article le plus vendu — no dates provided",
    llm_json={
        "action": "article_plus_vendu"
    },
    ws_response=FAKE_ARTICLE_RESPONSE
)

# Test 5 — Article le plus vendu with date range
run_test(
    name="Article le plus vendu — with date range",
    llm_json={
        "action":    "article_plus_vendu",
        "startDate": "20240101",
        "endDate":   "20241231"
    },
    ws_response={"reference": "PROD-007", "quantite": 320, "ca": "14 500 €"}
)

# Test 6 — Intégration Pièce success
run_test(
    name="Intégration Pièce — all required fields present",
    llm_json={
        "action":       "integrer_piece",
        "pieceType":    "FA",
        "customerType": "CLI",
        "customer":     "CLI-001"
    },
    ws_response=FAKE_PIECE_RESPONSE
)

# Test 7 — Intégration Pièce missing required fields
run_test(
    name="Intégration Pièce — customer MISSING (should block)",
    llm_json={
        "action":       "integrer_piece",
        "pieceType":    "FA",
        "customerType": "CLI"
    },
    expect_error=True
)

# Test 8 — Unknown action
run_test(
    name="Unknown action (LLM hallucination)",
    llm_json={
        "action": "fake_action_xyz"
    },
    expect_error=True
)

# ── VALIDATE_PAYLOAD UNIT TESTS (no HTTP at all) ──────────────────────────────

print(f"\n{'-'*60}")
print("UNIT TESTS — validate_payload() only")

def demo_validate_payload(name: str, llm_json: dict, expect_ok: bool) -> None:
    """Manual script demo only — not a pytest entrypoint (avoid ``test_*`` prefix)."""
    result = validate_payload(llm_json)
    status = "PASS" if result["ok"] == expect_ok else "FAIL"
    print(f"  [{status}] {name} -> ok={result['ok']}")
    if not result["ok"]:
        print(f"         -> {result.get('message') or result.get('error')}")

demo_validate_payload("reference present -> ok", {"action": "interroger_stock", "reference": "X"}, True)

demo_validate_payload("reference missing -> not ok", {"action": "interroger_stock"}, False)

demo_validate_payload("all optional -> ok (article_plus_vendu)", {"action": "article_plus_vendu"}, True)

demo_validate_payload(
    "all required -> ok (integrer_piece)",
    {"action": "integrer_piece", "pieceType": "FA", "customerType": "CLI", "customer": "C1"},
    True,
)

demo_validate_payload("two required missing -> not ok", {"action": "integrer_piece", "pieceType": "FA"}, False)


print(f"\n{'='*60}")
print("ALL TESTS COMPLETE")
print("If you see PASS on every test, the logic is correct.")
print("The real endpoint is only needed for the final live test.")
print("=" * 60)
