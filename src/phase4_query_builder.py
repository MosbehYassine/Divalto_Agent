"""
phase4_query_builder.py
=======================
Phase 4 specialized "WS Query Builder" module.

Input:
  - business request (natural language)
Output:
  - WS-conform payload selected from declared tools and completed by schema defaults
"""

from pathlib import Path
from typing import Any

from divalto_agent import validate_payload
from phase4_dataset import export_dataset_jsonl
from phase4_tools import TOOLS_REGISTRY
from phase4_prefunctions import (
    detect_region,
    extract_customer,
    extract_family,
    extract_reference,
)
from semantic_router import get_available_actions, resolve_measure, select_best_action


def _select_tool(user_request: str) -> tuple[str, dict[str, Any]]:
    """
    Select tool with deterministic weighted-scoring and return diagnostics.
    """
    selected_action, diagnostics = select_best_action(
        user_request,
        available_actions=get_available_actions(),
    )
    if not selected_action:
        diagnostics["selection_reason"] = "no_positive_signal"
        return "", diagnostics
    selected_tool = diagnostics.get("selected_tool") or selected_action
    return selected_tool, diagnostics


def build_ws_payload(user_request: str) -> dict[str, Any]:
    """
    Build a schema-compliant WS payload from business request text.
    """
    tool_name, diagnostics = _select_tool(user_request)
    selected_action = diagnostics.get("selected_action")
    if not selected_action:
        raise ValueError("No compatible action detected for this request.")
    matching_tool = next((tool for tool in TOOLS_REGISTRY.values() if tool.action == selected_action), None)
    if matching_tool is None:
        raise ValueError(f"No tool metadata found for action '{selected_action}'.")

    draft: dict[str, Any] = {"action": matching_tool.action}
    customer = extract_customer(user_request)
    reference = extract_reference(user_request)
    region = detect_region(user_request)
    family = extract_family(user_request)

    # Populate common semantic slots dynamically when fields exist.
    allowed_fields = set(matching_tool.optional_fields) | set(matching_tool.required_fields)

    if customer and "customer" in allowed_fields:
        draft["customer"] = customer
    if reference and "reference" in allowed_fields:
        draft["reference"] = reference
    if family and "family" in allowed_fields:
        draft["family"] = family
    if region and "region" in allowed_fields:
        draft["region"] = region

    if "warehouse" in matching_tool.optional_fields and "warehouse" not in draft:
        draft["warehouse"] = "*"
    if "status" in matching_tool.optional_fields and "status" not in draft:
        draft["status"] = "all"
    if "groupBy" in matching_tool.optional_fields and "groupBy" not in draft:
        draft["groupBy"] = "month"
    if "metric" in matching_tool.optional_fields and "metric" not in draft:
        metric_info = resolve_measure(user_request, available_actions=get_available_actions())
        draft["metric"] = metric_info["measure"] if metric_info["measure"] != "generic" else "sales"

    validated = validate_payload(draft)
    if not validated["ok"]:
        raise ValueError(validated.get("message") or validated.get("error") or "Payload validation failed.")
    return validated["data"]


def build_ws_payload_with_diagnostics(user_request: str) -> dict[str, Any]:
    """
    Build payload and return reliability metadata for observability.
    """
    tool_name, diagnostics = _select_tool(user_request)
    payload = build_ws_payload(user_request)
    diagnostics["selected_tool"] = tool_name
    diagnostics["selected_action"] = payload.get("action")
    return {"payload": payload, "diagnostics": diagnostics}


def build_ws_payload_guarded(user_request: str) -> dict[str, Any]:
    """
    Reliability-gated payload builder.
    If intent confidence is low, return a clarification request instead of payload.
    """
    try:
        result = build_ws_payload_with_diagnostics(user_request)
    except ValueError as exc:
        domains = sorted({tool.domain for tool in TOOLS_REGISTRY.values()})
        return {
            "ok": False,
            "requires_clarification": True,
            "clarification_message": str(exc),
            "suggested_domains": domains,
            "diagnostics": {
                "selected_action": None,
                "selected_tool": None,
                "confidence": "low",
                "score_margin": 0,
                "top_candidates": [],
            },
            "guard_reason": "no_detected_action",
        }
    confidence = result["diagnostics"].get("confidence", "low")
    score_margin = result["diagnostics"].get("score_margin", 0)
    is_ambiguous = confidence == "low" or score_margin < 2
    if is_ambiguous:
        domains = sorted({tool.domain for tool in TOOLS_REGISTRY.values()})
        return {
            "ok": False,
            "requires_clarification": True,
            "clarification_message": (
                "Votre demande est ambiguë ou trop proche entre plusieurs domaines. "
                "Précisez le domaine souhaité selon les capacités disponibles."
            ),
            "suggested_domains": domains,
            "diagnostics": result["diagnostics"],
            "guard_reason": (
                "low_confidence" if confidence == "low" else "low_margin_between_top_intents"
            ),
        }
    return {
        "ok": True,
        "requires_clarification": False,
        "payload": result["payload"],
        "diagnostics": result["diagnostics"],
    }


def build_training_ready_artifacts(dataset_dir: str) -> dict[str, str]:
    """
    Generate exportable dataset artifacts used for future fine-tuning.
    """
    dataset_path = str(Path(dataset_dir) / "phase4_plan_to_ws_dataset.jsonl")
    exported = export_dataset_jsonl(dataset_path)
    return {"dataset_jsonl": exported}
