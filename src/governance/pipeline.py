from __future__ import annotations

from typing import Any, Mapping

from governance.audit import build_run_record
from governance.execution_context import AgentExecutionContext
from governance.guards import PlanEvaluation, evaluate_plan


def run_with_governance_plan_check(plan: list[dict[str, Any]], policy) -> PlanEvaluation:
    """Thin wrapper retained for readability at call sites."""
    return evaluate_plan(policy, plan)


def finalize_agent_audit(
    exec_ctx: AgentExecutionContext | None,
    *,
    plan: list[dict[str, Any]],
    execution_result: Mapping[str, Any],
    final_answer: str | None,
    extra_governance_meta: Mapping[str, Any] | None = None,
) -> None:
    """
    Persists one JSONL row covering plan → ERP payloads → synthesized answer.

    ``execution_result`` is copied shallowly — ensure it does not include live secrets beyond
    payloads already sanitized by transports.
    """
    if exec_ctx is None or exec_ctx.audit_sink is None:
        return

    meta: dict[str, Any] = {
        "correlation_id": exec_ctx.correlation_id,
        "policy_mode": exec_ctx.policy.governance_enabled,
        "hitl_enforce": exec_ctx.policy.hitl_enforce,
        "signals": list(exec_ctx.governance_signals),
    }
    approval = exec_ctx.approval
    if approval:
        meta["approval_snapshot"] = {
            "allow_irreversible": approval.allow_irreversible,
            "approved_by": approval.approved_by,
        }
    if extra_governance_meta:
        meta.update(dict(extra_governance_meta))

    record = build_run_record(
        correlation_id=exec_ctx.correlation_id,
        user_query=exec_ctx.user_query,
        plan=list(plan),
        execution_result=dict(execution_result),
        final_answer=final_answer,
        started_monotonic=exec_ctx.started_monotonic,
        governance_meta=meta,
    )
    exec_ctx.audit_sink.emit(record)
