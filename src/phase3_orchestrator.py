"""
phase3_orchestrator.py
======================
Phase 3 — Step 2: The Orchestrator

Responsibility: execute a plan (list of WS steps) in order,
resolve {{step_N.field}} references between steps,
store intermediate results in memory,
return all collected results for the aggregator.

Reuses run_agent() from Phase 2 completely unchanged.
"""

import json
import re
from divalto_agent import validate_payload, get_token, call_webservice


# ─────────────────────────────────────────────
# REFERENCE RESOLVER
# ─────────────────────────────────────────────

def resolve_references(step: dict, memory: dict) -> dict:
    """
    Replace {{step_N.field}} placeholders with actual values
    collected from previous steps stored in memory.

    Example:
        step     = {"action": "interroger_stock",
                    "reference": "{{step_0.reference}}"}
        memory   = {"step_0": {"reference": "ALB0001", "quantite": 320}}
        returns  = {"action": "interroger_stock", "reference": "ALB0001"}
    """
    resolved = {}
    for key, value in step.items():
        if isinstance(value, str) and "{{" in value:
            # Extract step_N.field from {{step_N.field}}
            match = re.search(r'\{\{(\w+)\.(\w+)\}\}', value)
            if match:
                step_key  = match.group(1)   # e.g. "step_0"
                field_key = match.group(2)   # e.g. "reference"
                source    = memory.get(step_key, {})
                resolved[key] = source.get(field_key, value)
                placeholder = f"{{{{{step_key}.{field_key}}}}}"
                print(f"[Resolver] {key}: {placeholder} -> '{resolved[key]}'")
            else:
                resolved[key] = value
        else:
            resolved[key] = value
    return resolved


# ─────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────

def execute_plan(plan: list, token: str = None,
                 mock_responses: dict = None) -> dict:
    """
    Execute a list of WS call steps in order.

    Args:
        plan           : list of step dicts from the planner
        token          : pre-fetched auth token (optional,
                         fetched fresh if not provided)
        mock_responses : dict of step_N → fake ERP response
                         (for testing without real endpoint)

    Returns:
        {
          "ok":      True/False,
          "steps":   [ {step, action, raw_response}, ... ],
          "memory":  { "step_0": {...}, "step_1": {...} }
        }
    """
    memory  = {}
    steps   = []
    errors  = []

    # Get token once for all steps (unless mocking)
    if mock_responses is None:
        token = token or get_token()
        if not token:
            return {
                "ok":    False,
                "error": "Cannot obtain auth token.",
                "steps": [],
                "memory": {}
            }

    for step_def in plan:
        step_index = step_def.get("step", len(steps))
        step_key   = f"step_{step_index}"

        # 1. Resolve any references to previous results
        resolved = resolve_references(step_def, memory)
        action   = resolved.get("action")

        print(f"\n[Orchestrator] Executing {step_key}: {action}")
        print(f"[Orchestrator] Payload: {resolved}")

        # 2. Validate the step payload
        validation = validate_payload(dict(resolved))
        if not validation["ok"]:
            error_msg = validation.get("message") or validation.get("error")
            print(f"[Orchestrator] Validation failed: {error_msg}")
            errors.append({"step": step_index, "error": error_msg})
            # Non-blocking: store empty result and continue
            memory[step_key] = {}
            steps.append({
                "step":   step_index,
                "action": action,
                "ok":     False,
                "error":  error_msg,
                "raw":    {}
            })
            continue

        validated_data = validation["data"]

        # 3. Call WS (real or mock)
        if mock_responses is not None:
            # Mock mode: return fake response for this step
            raw_response = mock_responses.get(
                step_key,
                mock_responses.get("default", {"mock": True})
            )
            print(f"[Orchestrator] MOCK response: {raw_response}")
        else:
            # Production mode: call real Divalto endpoint
            raw_response = call_webservice(token, dict(validated_data))
            if raw_response is None:
                error_msg = f"WS call failed for action '{action}'"
                errors.append({"step": step_index, "error": error_msg})
                memory[step_key] = {}
                steps.append({
                    "step":   step_index,
                    "action": action,
                    "ok":     False,
                    "error":  error_msg,
                    "raw":    {}
                })
                continue

        # 4. Store in memory for next steps to reference
        memory[step_key] = raw_response
        steps.append({
            "step":   step_index,
            "action": action,
            "ok":     True,
            "raw":    raw_response
        })

        print(f"[Orchestrator] {step_key} complete -> stored in memory")

    return {
        "ok":     len(errors) == 0,
        "steps":  steps,
        "memory": memory,
        "errors": errors
    }
