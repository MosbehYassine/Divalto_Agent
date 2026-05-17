from __future__ import annotations

from governance.models import GovernancePolicy


def _parse_csv_set(raw: str) -> frozenset[str]:
    items = {part.strip() for part in (raw or "").split(",") if part.strip()}
    return frozenset(items)


def policy_from_settings(
    *,
    governance_enabled: bool,
    hitl_enforce: bool,
    allowed_actions_csv: str,
    denied_actions_csv: str,
    irreversible_actions_csv: str,
    strategic_customers_csv: str,
    invoice_amount_hitl_threshold: float,
) -> GovernancePolicy:
    """
    Build an immutable policy object from already-normalised settings values.
    """
    allowed = _parse_csv_set(allowed_actions_csv)
    denied = _parse_csv_set(denied_actions_csv)
    irreversible = _parse_csv_set(irreversible_actions_csv) or frozenset({"integrer_piece"})
    strategic = _parse_csv_set(strategic_customers_csv)
    allowed_opt: frozenset[str] | None = allowed if allowed else None
    return GovernancePolicy(
        governance_enabled=governance_enabled,
        hitl_enforce=hitl_enforce,
        allowed_actions=allowed_opt,
        denied_actions=denied,
        irreversible_actions=irreversible,
        strategic_customers=strategic,
        invoice_amount_hitl_threshold=invoice_amount_hitl_threshold,
    )
