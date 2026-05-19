from __future__ import annotations

import uuid
from pathlib import Path

from governance.audit import JsonlAuditSink
from governance.execution_context import AgentExecutionContext
from governance.models import ExecutionApproval
from governance.policy_loader import policy_from_settings


def build_execution_context(
    *,
    user_query: str | None,
    correlation_id: str | None,
    governance_enabled: bool,
    hitl_enforce: bool,
    audit_jsonl_path: str,
    allowed_actions_csv: str,
    denied_actions_csv: str,
    irreversible_actions_csv: str,
    strategic_customers_csv: str,
    invoice_amount_hitl_threshold: float,
    approval: ExecutionApproval | None,
) -> AgentExecutionContext | None:
    """
    Returns ``None`` when neither governance rules nor persistence hooks are requested.

    Audit logging can be enabled alone (policy checks remain permissive in that mode).
    """
    audit_sink: JsonlAuditSink | None = None
    raw_path = (audit_jsonl_path or "").strip()
    if raw_path:
        audit_sink = JsonlAuditSink(Path(raw_path).expanduser().resolve())

    if not governance_enabled and audit_sink is None:
        return None

    policy = policy_from_settings(
        governance_enabled=governance_enabled,
        hitl_enforce=hitl_enforce,
        allowed_actions_csv=allowed_actions_csv,
        denied_actions_csv=denied_actions_csv,
        irreversible_actions_csv=irreversible_actions_csv,
        strategic_customers_csv=strategic_customers_csv,
        invoice_amount_hitl_threshold=invoice_amount_hitl_threshold,
    )

    correlation = (correlation_id or "").strip() or str(uuid.uuid4())

    return AgentExecutionContext(
        correlation_id=correlation,
        user_query=user_query,
        policy=policy,
        approval=approval,
        audit_sink=audit_sink,
    )


def build_optional_context_from_env(
    *,
    user_query: str | None,
    correlation_id: str | None,
    approval: ExecutionApproval | None,
) -> AgentExecutionContext | None:
    """
    Convenience wrapper around environment-driven configuration.

    Imported lazily to keep ``settings.py`` free of circular imports toward governance.
    """
    import core.settings as app_settings  # defer import

    return build_execution_context(
        user_query=user_query,
        correlation_id=correlation_id,
        governance_enabled=app_settings.GOVERNANCE_ENABLED,
        hitl_enforce=app_settings.HITL_ENFORCE,
        audit_jsonl_path=app_settings.AUDIT_JSONL_PATH,
        allowed_actions_csv=app_settings.ALLOWED_WS_ACTIONS,
        denied_actions_csv=app_settings.DENIED_WS_ACTIONS,
        irreversible_actions_csv=app_settings.IRREVERSIBLE_WS_ACTIONS,
        strategic_customers_csv=app_settings.STRATEGIC_CUSTOMERS_CSV,
        invoice_amount_hitl_threshold=app_settings.INVOICE_HITL_THRESHOLD_EUR,
        approval=approval,
    )
