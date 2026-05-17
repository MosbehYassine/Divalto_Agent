import os
import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_SRC_DIR = _TESTS_DIR.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from semantic_routing import classic_semantic_analytics_eligible  # noqa: E402


def test_classic_semantic_eligible_for_aggregate_question(monkeypatch):
    monkeypatch.setenv("DIVALTO_SEMANTIC_ANALYTICS_IN_CLASSIC", "true")
    assert classic_semantic_analytics_eligible("Combien de ventes au total par mois ?") is True


def test_classic_semantic_not_eligible_for_chitchat(monkeypatch):
    monkeypatch.setenv("DIVALTO_SEMANTIC_ANALYTICS_IN_CLASSIC", "true")
    assert classic_semantic_analytics_eligible("Bonjour") is False


def test_classic_semantic_not_eligible_pure_stock_ref(monkeypatch):
    monkeypatch.setenv("DIVALTO_SEMANTIC_ANALYTICS_IN_CLASSIC", "true")
    assert classic_semantic_analytics_eligible("Quel est le stock de l'article ALB0001 ?") is False


def test_classic_semantic_not_eligible_client_count(monkeypatch):
    monkeypatch.setenv("DIVALTO_SEMANTIC_ANALYTICS_IN_CLASSIC", "true")
    assert classic_semantic_analytics_eligible("Combien au total des clients ?") is False


def test_classic_semantic_disabled(monkeypatch):
    monkeypatch.setenv("DIVALTO_SEMANTIC_ANALYTICS_IN_CLASSIC", "false")
    assert classic_semantic_analytics_eligible("Combien de clients au total ?") is False
