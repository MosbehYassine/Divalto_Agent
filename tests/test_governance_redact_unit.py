"""
Unit tests for audit redaction helper (Phase 6).
"""

import os
import sys

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from governance.audit import redact_secrets  # noqa: E402


def test_redact_flattens_password_fields():
    sample = {"user": "x", "password": "secret", "nested": {"token": "abc"}}
    out = redact_secrets(sample)
    assert out["password"] == "***REDACTED***"
    assert out["nested"]["token"] == "***REDACTED***"
    assert out["user"] == "x"


def test_redact_keeps_plain_numbers():
    assert redact_secrets({"total": 42}) == {"total": 42}
