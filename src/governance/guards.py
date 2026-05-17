from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from governance.models import ExecutionApproval, GovernancePolicy, HitlCategory


@dataclass(frozen=True)
class PlanEvaluation:
    ok: bool
    code: str
    message: str
    hitl_reasons: tuple[str, ...] = ()


def evaluate_plan(policy: GovernancePolicy, plan: list[Mapping[str, Any]]) -> PlanEvaluation:
    """
    Static plan checks: denied tools, out-of-allowlist actions, empty plans.
    """
    if not policy.governance_enabled:
        return PlanEvaluation(ok=True, code="GOV_DISABLED", message="Governance checks skipped.")

    if not plan:
        return PlanEvaluation(ok=False, code="EMPTY_PLAN", message="Plan vide — exécution refusée.")

    reasons: list[str] = []
    for step in plan:
        action = step.get("action")
        if not action:
            return PlanEvaluation(
                ok=False,
                code="MISSING_ACTION",
                message="Étape sans champ action.",
                hitl_reasons=tuple(reasons),
            )
        if action in policy.denied_actions:
            return PlanEvaluation(
                ok=False,
                code="ACTION_DENIED",
                message=f"Action '{action}' explicitement interdite par la politique.",
                hitl_reasons=tuple(reasons),
            )
        if policy.allowed_actions is not None and action not in policy.allowed_actions:
            return PlanEvaluation(
                ok=False,
                code="ACTION_NOT_ALLOWED",
                message=f"Action '{action}' hors périmètre autorisé.",
                hitl_reasons=tuple(reasons),
            )
    return PlanEvaluation(ok=True, code="OK", message="Plan accepté.", hitl_reasons=tuple(reasons))


@dataclass(frozen=True)
class PreStepResult:
    allow_call: bool
    code: str
    message: str
    hitl_category: HitlCategory | None = None
    advisories: tuple[str, ...] = ()


def _is_strategic_customer(policy: GovernancePolicy, payload: Mapping[str, Any]) -> bool:
    customer = str(payload.get("customer") or "").strip().upper()
    if not customer or not policy.strategic_customers:
        return False
    return any(customer.startswith(seg.upper()) for seg in policy.strategic_customers)


def pre_step_gate(
    policy: GovernancePolicy,
    approval: ExecutionApproval | None,
    *,
    action: str | None,
    payload: Mapping[str, Any],
) -> PreStepResult:
    """
    Pre-WS decisioning: irreversible writes require explicit approval when enforcement is on.
    Strategic customer reads are flagged (advisory unless combined with future rules).
    """
    if not policy.governance_enabled:
        return PreStepResult(True, "GOV_DISABLED", "Governance disabled.")

    if not action:
        return PreStepResult(False, "MISSING_ACTION", "Action manquante.", HitlCategory.POLICY_BLOCK)

    advisories: list[str] = []
    if _is_strategic_customer(policy, payload):
        if policy.hitl_enforce:
            return PreStepResult(
                False,
                "HITL_STRATEGIC_CUSTOMER",
                "Client stratégique — intervention humaine requise avant appel.",
                HitlCategory.STRATEGIC_CUSTOMER,
            )
        advisories.append("STRATEGIC_CUSTOMER_TOUCH")

    if action in policy.irreversible_actions:
        allowed = bool(approval and approval.allow_irreversible)
        if policy.hitl_enforce and not allowed:
            return PreStepResult(
                False,
                "HITL_IRREVERSIBLE",
                "Action irréversible — approbation opérateur manquante.",
                HitlCategory.IRREVERSIBLE_WRITE,
            )

    return PreStepResult(True, "OK", "Étape autorisée.", advisories=tuple(advisories))


def post_step_triggers(
    policy: GovernancePolicy,
    *,
    action: str | None,
    raw: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """
    Post-call advisory triggers (e.g. high invoice exposure) for audit + KPI.
    Does not mutate ERP data.
    """
    signals: list[dict[str, Any]] = []
    if not policy.governance_enabled:
        return signals

    if action == "consulter_facturation":
        try:
            amount = float(raw.get("montantTotal") or 0.0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount >= policy.invoice_amount_hitl_threshold:
            signals.append(
                {
                    "category": HitlCategory.HIGH_VALUE_READ.value,
                    "message": "Montant facturation élevé — revue humaine recommandée.",
                    "details": {"montantTotal": amount, "threshold": policy.invoice_amount_hitl_threshold},
                }
            )
    return signals
