import os
import sys

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import time

import phase3_planner as p3  # noqa: E402
import phase5_planner as p5  # noqa: E402


def test_phase3_llm_plan_normalizes_step_indices(monkeypatch):
    def fake_call_ollama_json_plan(**kwargs):
        return [{"action": "interroger_stock", "reference": "ALB0001"}]

    monkeypatch.setattr(p3, "call_ollama_json_plan", fake_call_ollama_json_plan)
    monkeypatch.setattr(p3, "retrieve_context", lambda _q: {"context": "[source:test]\npolicy"})
    plan = p3.llm_plan("Quel est le stock ALB0001 ?")
    assert plan[0]["step"] == 0
    assert plan[0]["action"] == "interroger_stock"


def test_phase5_llm_plan_normalizes_step_indices(monkeypatch):
    def fake_call_ollama_json_plan(**kwargs):
        return [{"action": "consulter_indicateurs_analytiques", "metric": "sales"}]

    monkeypatch.setattr(p5, "call_ollama_json_plan", fake_call_ollama_json_plan)
    monkeypatch.setattr(p5, "retrieve_context", lambda _q: {"context": "[source:test]\nkpi"})
    plan = p5.llm_plan_phase5("Montre tendance ventes")
    assert plan[0]["step"] == 0
    assert plan[0]["action"] == "consulter_indicateurs_analytiques"


def test_phase3_client_count_never_calls_llm_when_real_planner(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("Ollama planner must not run for deterministic client count")

    monkeypatch.setattr(p3, "llm_plan", boom)
    out = p3.plan("Combien au total des clients ?", use_mock=False)
    assert out[0]["action"] == "consulter_clients"
    assert out[0].get("aggregate") == "count"


def test_phase3_llm_plan_times_out_to_mock(monkeypatch):
    monkeypatch.setenv("DIVALTO_LLM_PLAN_TIMEOUT_SECONDS", "0.15")

    def slow_llm(_q):
        time.sleep(0.8)
        return [{"step": 0, "action": "interroger_stock", "reference": "X"}]

    monkeypatch.setattr(p3, "llm_plan", slow_llm)
    # Deterministic mock_plan returns ranking when LLM is skipped by timeout.
    out = p3.plan("classement des ventes du mois", use_mock=False)
    assert isinstance(out, list) and len(out) >= 1
    assert out[0].get("action") == "classement_ventes"


def test_phase3_llm_plan_injects_rag_context(monkeypatch):
    captured = {}

    def fake_call_ollama_json_plan(**kwargs):
        captured["prompt"] = kwargs["system_prompt"]
        return [{"step": 0, "action": "interroger_stock", "reference": "ALB0001"}]

    monkeypatch.setattr(p3, "call_ollama_json_plan", fake_call_ollama_json_plan)
    monkeypatch.setattr(p3, "retrieve_context", lambda _q: {"context": "[source:x]\nRegle stock"})
    p3.llm_plan("stock article")
    assert "Contexte métier récupéré (RAG)" in captured["prompt"]
