from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet


class HitlCategory(str, Enum):
    """Human-in-the-loop classification for audit / KPI rollups."""

    IRREVERSIBLE_WRITE = "irreversible_write"
    STRATEGIC_CUSTOMER = "strategic_customer"
    HIGH_VALUE_READ = "high_value_read"
    POLICY_BLOCK = "policy_block"


@dataclass(frozen=True)
class ExecutionApproval:
    """
    Explicit operator consent for sensitive execution paths.

    Wire this from your operator console / workflow engine in production.
    """

    allow_irreversible: bool = False
    approved_by: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class GovernancePolicy:
    """
    Centralised policy flags — loaded from environment via ``from_settings``.
    """

    governance_enabled: bool = False
    hitl_enforce: bool = False
    allowed_actions: FrozenSet[str] | None = None
    denied_actions: FrozenSet[str] = frozenset()
    irreversible_actions: FrozenSet[str] = field(
        default_factory=lambda: frozenset({"integrer_piece"})
    )
    strategic_customers: FrozenSet[str] = frozenset()
    invoice_amount_hitl_threshold: float = 50_000.0

    @staticmethod
    def permissive() -> "GovernancePolicy":
        """No blocking rules; useful when only audit logging is enabled."""
        return GovernancePolicy(governance_enabled=False, hitl_enforce=False)
