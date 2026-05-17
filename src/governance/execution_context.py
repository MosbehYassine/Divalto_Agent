from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from governance.audit import JsonlAuditSink
from governance.models import ExecutionApproval, GovernancePolicy


@dataclass(slots=True)
class AgentExecutionContext:
    """
    Cross-cutting runtime bag passed into ``execute_plan`` and higher-level runners.

    Keeping this object immutable where possible simplifies reasoning about audits.
    """

    correlation_id: str
    user_query: str | None = None
    policy: GovernancePolicy = field(default_factory=GovernancePolicy.permissive)
    approval: ExecutionApproval | None = None
    audit_sink: JsonlAuditSink | None = None
    started_monotonic: float = field(default_factory=perf_counter)
    governance_signals: list[dict[str, Any]] = field(default_factory=list)
