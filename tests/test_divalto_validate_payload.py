"""
Unit tests for Phase 2 payload validation (no HTTP).
"""

import os
import sys

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import pytest  # noqa: E402

from divalto_agent import validate_payload  # noqa: E402


@pytest.mark.parametrize(
    "payload,expect_ok",
    [
        ({"action": "interroger_stock", "reference": "X"}, True),
        ({"action": "interroger_stock"}, False),
        ({"action": "article_plus_vendu"}, True),
        (
            {"action": "integrer_piece", "pieceType": "FA", "customerType": "CLI", "customer": "C1"},
            True,
        ),
        ({"action": "integrer_piece", "pieceType": "FA"}, False),
        ({"action": "classement_ventes"}, True),
        ({"action": "fake_action"}, False),
    ],
)
def test_validate_payload_matrix(payload: dict, expect_ok: bool) -> None:
    result = validate_payload(payload)
    assert result["ok"] is expect_ok


def test_classement_fills_limit_default() -> None:
    result = validate_payload({"action": "classement_ventes"})
    assert result["ok"] is True
    assert result["data"]["limit"] == 5
