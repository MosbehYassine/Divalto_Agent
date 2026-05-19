"""
phase4_agent.py
===============
Phase 4 orchestrator for industrialized tooling + dataset artifacts.
"""

import json
from pathlib import Path
from typing import Any

from analytics.catalog import load_or_build_semantic_bundle
from analytics.orchestrator import run_semantic_data_analytics
from phase4.query_builder import build_training_ready_artifacts, build_ws_payload_guarded
from phase4.tools import list_tools


def run_phase4(user_request: str, dataset_output_dir: str | None = None) -> dict[str, Any]:
    """
    Build a full Phase 4 structured output:
      - declared tools registry
      - generated WS payload
      - dataset artifact export path
    """
    output_dir = dataset_output_dir or str(Path(__file__).resolve().parents[2] / "datasets")
    guarded = build_ws_payload_guarded(user_request)
    artifacts = build_training_ready_artifacts(output_dir)
    response: dict[str, Any] = {
        "tools": list_tools(),
        "ok": guarded["ok"],
        "requires_clarification": guarded["requires_clarification"],
        "diagnostics": guarded["diagnostics"],
        "artifacts": artifacts,
    }

    bundle, _, semantic_notes = load_or_build_semantic_bundle()
    analytics_ok = False
    if bundle:
        analytics = run_semantic_data_analytics(user_request)
        response["semantic_notes"] = semantic_notes
        response["semantic_analytics"] = analytics
        analytics_ok = bool(analytics.get("ok"))
        if analytics_ok and analytics.get("answer"):
            response["answer"] = analytics["answer"]

    if guarded["ok"]:
        response["payload"] = guarded["payload"]
    else:
        response["clarification_message"] = guarded["clarification_message"]
        response["suggested_domains"] = guarded["suggested_domains"]
        response["guard_reason"] = guarded["guard_reason"]

    if not response.get("answer"):
        if guarded["ok"] and guarded.get("payload"):
            response["answer"] = json.dumps(
                {"phase": "query_builder", "action": guarded["payload"].get("action")},
                ensure_ascii=False,
            )
        elif response.get("semantic_analytics", {}).get("answer"):
            response["answer"] = response["semantic_analytics"]["answer"]
        elif response.get("semantic_analytics", {}).get("error"):
            response["answer"] = f"Analytique: {response['semantic_analytics']['error']}"
        else:
            response["answer"] = response.get("clarification_message") or "Aucune réponse structurée disponible."

    response["ok"] = bool(guarded["ok"]) or analytics_ok
    return response


if __name__ == "__main__":
    demo_query = "Donne la facturation du client CLI-001."
    result = run_phase4(demo_query)
    print(json.dumps(result, ensure_ascii=False, indent=2))
