import json
import os
import sys

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from governance.context import build_execution_context  # noqa: E402
from governance.execution_context import AgentExecutionContext  # noqa: E402
from governance.kpi import summarize_audit_file  # noqa: E402
from governance.pipeline import finalize_agent_audit  # noqa: E402
from phase3_orchestrator import execute_plan  # noqa: E402


def test_plan_denies_blocked_action(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    ctx = build_execution_context(
        user_query="test",
        correlation_id="corr-plan",
        governance_enabled=True,
        hitl_enforce=False,
        audit_jsonl_path=str(audit_path),
        allowed_actions_csv="",
        denied_actions_csv="integrer_piece",
        irreversible_actions_csv="integrer_piece",
        strategic_customers_csv="",
        invoice_amount_hitl_threshold=50_000,
        approval=None,
    )
    assert isinstance(ctx, AgentExecutionContext)
    plan = [
        {
            "step": 0,
            "action": "integrer_piece",
            "pieceType": "SO",
            "customerType": "CLI",
            "customer": "CLI-1",
        }
    ]
    result = execute_plan(plan, mock_responses={"step_0": {"pieceId": "X"}}, execution_context=ctx)
    assert result["governance"]["plan_blocked"] is True
    assert result["steps"] == []


def test_irreversible_requires_approval_when_enforced(tmp_path):
    audit_path = tmp_path / "audit-enforce.jsonl"
    ctx = build_execution_context(
        user_query="irreversible",
        correlation_id="corr-hitl",
        governance_enabled=True,
        hitl_enforce=True,
        audit_jsonl_path=str(audit_path),
        allowed_actions_csv="",
        denied_actions_csv="",
        irreversible_actions_csv="integrer_piece",
        strategic_customers_csv="",
        invoice_amount_hitl_threshold=50_000,
        approval=None,
    )
    plan = [
        {
            "step": 0,
            "action": "integrer_piece",
            "pieceType": "SO",
            "customerType": "CLI",
            "customer": "CLI-2",
        }
    ]
    result = execute_plan(plan, mock_responses={"step_0": {"pieceId": "X"}}, execution_context=ctx)
    assert result["ok"] is False
    stub_step = next(step for step in result["steps"] if step["action"] == "integrer_piece")
    assert stub_step["ok"] is False


def test_audit_roundtrip_writes_jsonl(tmp_path):
    audit_path = tmp_path / "audit-complete.jsonl"
    ctx = build_execution_context(
        user_query="roundtrip",
        correlation_id="corr-audit",
        governance_enabled=False,
        hitl_enforce=False,
        audit_jsonl_path=str(audit_path),
        allowed_actions_csv="",
        denied_actions_csv="",
        irreversible_actions_csv="integrer_piece",
        strategic_customers_csv="",
        invoice_amount_hitl_threshold=50_000,
        approval=None,
    )
    assert ctx.audit_sink is not None

    plan = [{"step": 0, "action": "interroger_stock", "reference": "ABC", "warehouse": "*"}]
    result = execute_plan(plan, mock_responses={"step_0": {"reference": "ABC", "warehouse": "*", "quantity": 9}}, execution_context=ctx)

    finalize_agent_audit(
        ctx,
        plan=plan,
        execution_result=result,
        final_answer="stock répondue",
        extra_governance_meta={"mode": "test"},
    )

    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines, "audit file should contain a row"
    payload = json.loads(lines[-1])
    assert payload["correlation_id"] == "corr-audit"
    assert payload["final_answer"].startswith("stock")


def test_kpi_summary_counts(tmp_path):
    audit_file = tmp_path / "rollup.jsonl"
    record = {
        "duration_ms": 120,
        "execution": {"steps": [{"ok": True}, {"ok": False}], "governance": {}},
        "governance": {"signals": [{"type": "X"}]},
    }
    audit_file.write_text(json.dumps(record) + "\n", encoding="utf-8")
    summary = summarize_audit_file(str(audit_file), max_records=10)
    assert summary.runs == 1
    assert summary.ws_attempts == 2
    assert summary.ws_failures == 1
