"""
phase3_orchestrator.py
======================
Phase 3 — Step 2: The Orchestrator

Responsibility: execute a plan (list of WS steps) in order,
resolve {{step_N.field}} placeholders between steps,
store intermediate results in memory,
return collected results for the aggregator.

Phase 6 hooks (optional): perimeter validation, irreversible safeguards,
and structured governance metadata attached to every response.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Mapping

from core.divalto_agent import get_token, validate_payload
from core.erp_backend import get_erp_backend
from core.settings import USE_SQLITE_MOCK

from governance.execution_context import AgentExecutionContext
from governance.guards import evaluate_plan, post_step_triggers, pre_step_gate

logger = logging.getLogger(__name__)


def resolve_references(step: dict, memory: dict) -> dict[str, Any]:
    """
    Replace {{step_N.field}} placeholders with concrete values sourced from memory.

    Example:
        step = {"action": "interroger_stock", "reference": "{{step_0.reference}}"}
        memory = {"step_0": {"reference": "ALB0001", "quantite": 320}}
        returns resolved dict with injected reference string.
    """
    resolved: dict[str, Any] = {}
    for key, value in step.items():
        if isinstance(value, str) and "{{" in value:
            match = re.search(r"\{\{(\w+)\.(\w+)\}\}", value)
            if match:
                step_key = match.group(1)
                field_key = match.group(2)
                source = memory.get(step_key, {})
                resolved[key] = source.get(field_key, value)
                placeholder = f"{{{{{step_key}.{field_key}}}}}"
                logger.info("[Resolver] %s: %s -> '%s'", key, placeholder, resolved[key])
            else:
                resolved[key] = value
        else:
            resolved[key] = value
    return resolved


def execute_plan(
    plan: list[dict[str, Any]],
    token: str | None = None,
    mock_responses: dict[str, Any] | None = None,
    *,
    execution_context: AgentExecutionContext | None = None,
) -> dict[str, Any]:
    """
    Execute an ordered WS plan.

    Additional kwargs:
        execution_context — optional Phase 6 tracing / guard rail context.
    """
    memory: dict[str, Any] = {}
    steps: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    governance_flags: dict[str, Any] = {"plan_blocked": False}

    if execution_context:
        governance_flags.update(
            {
                "plan_blocked": False,
                "correlation_id": execution_context.correlation_id,
            }
        )

    ctx = execution_context
    policy = ctx.policy if ctx else None

    if policy and policy.governance_enabled:
        plan_eval = evaluate_plan(policy, plan)
        if not plan_eval.ok:
            governance_flags.update(
                {
                    "plan_blocked": True,
                    "code": plan_eval.code,
                    "message": plan_eval.message,
                }
            )
            return {
                "ok": False,
                "error": plan_eval.message,
                "steps": [],
                "memory": {},
                "errors": [{"scope": "plan", "code": plan_eval.code, "message": plan_eval.message}],
                "governance": governance_flags,
            }

    token_for_calls: str | None = token
    if mock_responses is None:
        # In SQLite mock mode, Phase 2 backend does not require auth.
        # Skipping token acquisition avoids false failures when no auth endpoint is configured.
        if USE_SQLITE_MOCK:
            token_for_calls = token_for_calls or "sqlite-mock-token"
        else:
            token_for_calls = token_for_calls or get_token()

        if not token_for_calls:
            failure_signal = {"type": "AUTH_FAILURE", "message": "Token indisponible."}
            if execution_context:
                execution_context.governance_signals.append(failure_signal)
            else:
                governance_flags.setdefault("signals", []).append(failure_signal)
            return {
                "ok": False,
                "error": "Cannot obtain auth token.",
                "steps": [],
                "memory": {},
                "errors": [],
                "governance": governance_flags,
            }

    for step_def in plan:
        step_index = int(step_def.get("step", len(steps)))
        step_key = f"step_{step_index}"

        resolved = resolve_references(step_def, memory)
        action = resolved.get("action")

        logger.info("\n[Orchestrator] Executing %s: %s", step_key, action)
        logger.info("[Orchestrator] Payload: %s", json.dumps(resolved, ensure_ascii=False, default=str))

        validation = validate_payload(dict(resolved))
        if not validation["ok"]:
            error_msg = validation.get("message") or validation.get("error") or "Validation error"
            logger.warning("[Orchestrator] Validation failed: %s", error_msg)
            errors.append({"step": step_index, "error": error_msg})
            memory[step_key] = {}
            steps.append(
                {
                    "step": step_index,
                    "action": action,
                    "ok": False,
                    "error": error_msg,
                    "raw": {},
                    "payload_snapshot": {k: v for k, v in dict(resolved).items() if k != "step"},
                }
            )
            continue

        validated_data = validation["data"]
        payload_snapshot = dict(validated_data)

        allow_call = True
        gate_reason = ""

        if ctx:
            gate = pre_step_gate(
                ctx.policy,
                ctx.approval,
                action=action,
                payload=payload_snapshot,
            )
            allow_call = gate.allow_call
            gate_reason = gate.message or ""

            if gate.advisories:
                ctx.governance_signals.extend(
                    {
                        "type": advisory,
                        "step": step_index,
                        "action": action,
                    }
                    for advisory in gate.advisories
                )

        policy_active = policy and policy.governance_enabled
        if policy_active and ctx and not allow_call:
            error_msg = gate_reason or "Human review required."
            logger.warning("[Orchestrator] Policy gate aborted step: %s", error_msg)
            errors.append({"step": step_index, "error": error_msg})
            ctx.governance_signals.append(
                {
                    "type": "POLICY_GATE",
                    "detail": gate_reason or "blocked",
                    "step": step_index,
                    "action": action,
                }
            )
            memory[step_key] = {}
            steps.append(
                {
                    "step": step_index,
                    "action": action,
                    "ok": False,
                    "error": error_msg,
                    "raw": {},
                    "payload_snapshot": payload_snapshot,
                }
            )
            continue

        if mock_responses is not None:
            raw_response = mock_responses.get(
                step_key,
                mock_responses.get("default", {"mock": True}),
            )
            logger.debug("[Orchestrator] MOCK response: %s", raw_response)
        else:
            backend = get_erp_backend(token_for_calls or "")
            try:
                raw_response = backend.execute(action, dict(validated_data))
            except Exception as exc:  # noqa: BLE001
                error_msg = str(exc) or f"WS call failed for action '{action}'"
                errors.append({"step": step_index, "error": error_msg})
                memory[step_key] = {}
                steps.append(
                    {
                        "step": step_index,
                        "action": action,
                        "ok": False,
                        "error": error_msg,
                        "raw": {},
                        "payload_snapshot": payload_snapshot,
                    }
                )
                continue
            if raw_response is None:
                error_msg = f"WS call failed for action '{action}'"
                errors.append({"step": step_index, "error": error_msg})
                memory[step_key] = {}
                steps.append(
                    {
                        "step": step_index,
                        "action": action,
                        "ok": False,
                        "error": error_msg,
                        "raw": {},
                        "payload_snapshot": payload_snapshot,
                    }
                )
                continue

        if ctx and policy and isinstance(raw_response, Mapping):
            ctx.governance_signals.extend(post_step_triggers(policy, action=action, raw=raw_response))

        memory[step_key] = raw_response
        steps.append(
            {
                "step": step_index,
                "action": action,
                "ok": True,
                "raw": raw_response,
                "payload_snapshot": payload_snapshot,
            }
        )

        logger.info("[Orchestrator] %s complete -> stored in memory", step_key)

    result_ok = len(errors) == 0

    governance_flags.setdefault("signals", [])
    if execution_context:
        governance_flags.update(
            {
                "signals": list(execution_context.governance_signals),
                "signals_count": len(execution_context.governance_signals),
            }
        )

    return {
        "ok": result_ok,
        "steps": steps,
        "memory": memory,
        "errors": errors,
        "governance": governance_flags,
    }
