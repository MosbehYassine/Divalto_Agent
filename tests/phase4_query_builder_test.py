"""
phase4_query_builder_test.py
============================
Phase 4 tests:
  - official WS tool declaration coverage
  - payload conformity from business requests
  - dataset artifact generation
"""

import os
import sys
from pathlib import Path


CURRENT_DIR = os.path.dirname(__file__)
SRC_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from phase4_agent import run_phase4  # noqa: E402
from phase4_query_builder import (  # noqa: E402
    build_training_ready_artifacts,
    build_ws_payload,
    build_ws_payload_guarded,
    build_ws_payload_with_diagnostics,
)
from phase4_tools import TOOLS_REGISTRY, get_tool_by_action  # noqa: E402


def test_tools_registry_contains_phase4_domains() -> None:
    actions = {tool.action for tool in TOOLS_REGISTRY.values()}
    expected_actions = {
        "consulter_facturation",
        "consulter_ventes",
        "consulter_articles",
        "consulter_clients",
        "consulter_stocks",
        "consulter_indicateurs_analytiques",
    }
    assert expected_actions.issubset(actions)


def test_action_lookup_round_trip() -> None:
    tool = get_tool_by_action("consulter_facturation")
    assert tool is not None
    assert tool.tool_name == "facturation"


def test_build_ws_payload_facturation() -> None:
    payload = build_ws_payload("Montre la facturation du client CLI-001")
    assert payload["action"] == "consulter_facturation"
    assert payload["customer"] == "CLI-001"
    assert payload["status"] == "all"


def test_build_ws_payload_stocks() -> None:
    payload = build_ws_payload("Quel est le stock de ALB0001 ?")
    assert payload["action"] in {"consulter_stocks", "interroger_stock"}
    assert payload["reference"] == "ALB0001"
    if "warehouse" in payload:
        assert payload["warehouse"] == "*"


def test_build_ws_payload_clients_with_region() -> None:
    payload = build_ws_payload("Liste les clients de la region nord")
    assert payload["action"] == "consulter_clients"
    assert payload["region"] == "NORD"


def test_build_training_artifacts(tmp_path: Path) -> None:
    artifacts = build_training_ready_artifacts(str(tmp_path))
    dataset_path = Path(artifacts["dataset_jsonl"])
    assert dataset_path.exists()
    assert dataset_path.read_text(encoding="utf-8").strip() != ""


def test_build_ws_payload_with_diagnostics_has_confidence() -> None:
    result = build_ws_payload_with_diagnostics("Montre les indicateurs KPI de ventes")
    assert result["payload"]["action"] in {
        "consulter_indicateurs_analytiques",
        "consulter_ventes",
    }
    assert result["diagnostics"]["confidence"] in {"low", "medium", "high"}
    assert len(result["diagnostics"]["top_candidates"]) > 0


def test_run_phase4_full_output(tmp_path: Path) -> None:
    result = run_phase4(
        "Donne les ventes du client CLI-001",
        dataset_output_dir=str(tmp_path),
    )
    assert "tools" in result and len(result["tools"]) >= 6
    assert result["ok"] is True
    assert result["requires_clarification"] is False
    assert "diagnostics" in result
    assert result["diagnostics"]["selected_action"] == result["payload"]["action"]
    assert result["payload"]["action"] == "consulter_ventes"
    assert Path(result["artifacts"]["dataset_jsonl"]).exists()


def test_guarded_builder_requests_clarification_on_low_confidence() -> None:
    guarded = build_ws_payload_guarded("Bonjour")
    assert guarded["ok"] is False
    assert guarded["requires_clarification"] is True
    assert "clarification_message" in guarded
    assert guarded["guard_reason"] in {"low_confidence", "no_detected_action"}


def test_guarded_builder_requests_clarification_on_low_margin() -> None:
    guarded = build_ws_payload_guarded("Montre le client et le stock")
    assert guarded["ok"] is False
    assert guarded["requires_clarification"] is True
    assert guarded["guard_reason"] in {
        "low_margin_between_top_intents",
        "low_confidence",
        "no_detected_action",
    }


def test_run_phase4_returns_clarification_structure(tmp_path: Path) -> None:
    result = run_phase4("Salut", dataset_output_dir=str(tmp_path))
    assert result["ok"] is False
    assert result["requires_clarification"] is True
    assert "clarification_message" in result
    assert "suggested_domains" in result
    assert "guard_reason" in result
