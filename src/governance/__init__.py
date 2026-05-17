"""
Governance & traceability (Phase 6) — policy guards, HITL signals, audit sink.

This package is intentionally decoupled from ERP transport: the orchestrator
calls into small, testable hooks without importing Divalto HTTP details.
"""

from governance.audit import JsonlAuditSink, build_run_record, redact_secrets
from governance.context import build_execution_context, build_optional_context_from_env
from governance.execution_context import AgentExecutionContext
from governance.guards import PlanEvaluation, evaluate_plan, post_step_triggers, pre_step_gate
from governance.kpi import AuditAggregate, summarize_audit_file
from governance.models import ExecutionApproval, GovernancePolicy
from governance.pipeline import finalize_agent_audit, run_with_governance_plan_check

__all__ = [
    "AgentExecutionContext",
    "AuditAggregate",
    "ExecutionApproval",
    "GovernancePolicy",
    "JsonlAuditSink",
    "PlanEvaluation",
    "build_execution_context",
    "build_optional_context_from_env",
    "build_run_record",
    "evaluate_plan",
    "finalize_agent_audit",
    "post_step_triggers",
    "pre_step_gate",
    "redact_secrets",
    "run_with_governance_plan_check",
    "summarize_audit_file",
]
