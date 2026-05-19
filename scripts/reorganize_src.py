#!/usr/bin/env python3
"""One-shot reorganize agent_project/src into modules. Run from agent_project/."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

MOVES: list[tuple[str, str]] = [
    ("settings.py", "core/settings.py"),
    ("console_utils.py", "core/console_utils.py"),
    ("intent_contract.py", "core/intent_contract.py"),
    ("pipeline_router.py", "core/pipeline_router.py"),
    ("erp_backend.py", "core/erp_backend.py"),
    ("feedback_store.py", "core/feedback_store.py"),
    ("prompt_templates.py", "core/prompt_templates.py"),
    ("divalto_agent.py", "core/divalto_agent.py"),
    ("sqlite_backend.py", "core/sqlite_backend.py"),
    ("semantic_router.py", "routing/semantic_router.py"),
    ("semantic_routing.py", "routing/semantic_routing.py"),
    ("ollama_client.py", "llm/ollama_client.py"),
    ("rag_retriever.py", "llm/rag_retriever.py"),
    ("phase3_agent.py", "phase3/agent.py"),
    ("phase3_planner.py", "phase3/planner.py"),
    ("phase3_orchestrator.py", "phase3/orchestrator.py"),
    ("phase4_agent.py", "phase4/agent.py"),
    ("phase4_dataset.py", "phase4/dataset.py"),
    ("phase4_prefunctions.py", "phase4/prefunctions.py"),
    ("phase4_query_builder.py", "phase4/query_builder.py"),
    ("phase4_tools.py", "phase4/tools.py"),
    ("phase5_agent.py", "phase5/agent.py"),
    ("phase5_analytics.py", "phase5/analytics.py"),
    ("phase5_dates.py", "phase5/dates.py"),
    ("phase5_planner.py", "phase5/planner.py"),
    ("analytic_catalog.py", "analytics/catalog.py"),
    ("analytic_compiler.py", "analytics/compiler.py"),
    ("analytic_orchestrator.py", "analytics/orchestrator.py"),
    ("auto_olap_pipeline.py", "analytics/auto_olap_pipeline.py"),
    ("mdx_executor.py", "analytics/mdx_executor.py"),
    ("full_auto_run.py", "analytics/full_auto_run.py"),
    ("langgraph_agent.py", "agents/langgraph_agent.py"),
    ("api_server.py", "app/server.py"),
    ("ws_schemas.json", "config/ws_schemas.json"),
]

_seen: set[str] = set()
MOVES_CLEAN: list[tuple[str, str]] = []
for old, new in MOVES:
    if old in _seen:
        continue
    if (SRC / old).exists():
        _seen.add(old)
        MOVES_CLEAN.append((old, new))
    elif old == "ws_schemas.json" and (SRC / old).exists():
        _seen.add(old)
        MOVES_CLEAN.append((old, new))
MOVES = MOVES_CLEAN

IMPORT_REPLACEMENTS: list[tuple[str, str]] = [
    ("from phase3_orchestrator", "from phase3.orchestrator"),
    ("from phase3_planner", "from phase3.planner"),
    ("from phase3_agent", "from phase3.agent"),
    ("from phase4_query_builder", "from phase4.query_builder"),
    ("from phase4_prefunctions", "from phase4.prefunctions"),
    ("from phase4_dataset", "from phase4.dataset"),
    ("from phase4_tools", "from phase4.tools"),
    ("from phase4_agent", "from phase4.agent"),
    ("from phase5_planner", "from phase5.planner"),
    ("from phase5_analytics", "from phase5.analytics"),
    ("from phase5_dates", "from phase5.dates"),
    ("from phase5_agent", "from phase5.agent"),
    ("from analytic_orchestrator", "from analytics.orchestrator"),
    ("from analytic_compiler", "from analytics.compiler"),
    ("from analytic_catalog", "from analytics.catalog"),
    ("from auto_olap_pipeline", "from analytics.auto_olap_pipeline"),
    ("from mdx_executor", "from analytics.mdx_executor"),
    ("from full_auto_run", "from analytics.full_auto_run"),
    ("from langgraph_agent", "from agents.langgraph_agent"),
    ("from semantic_routing", "from routing.semantic_routing"),
    ("from semantic_router", "from routing.semantic_router"),
    ("from ollama_client", "from llm.ollama_client"),
    ("from rag_retriever", "from llm.rag_retriever"),
    ("from pipeline_router", "from core.pipeline_router"),
    ("from intent_contract", "from core.intent_contract"),
    ("from console_utils", "from core.console_utils"),
    ("from feedback_store", "from core.feedback_store"),
    ("from prompt_templates", "from core.prompt_templates"),
    ("from erp_backend", "from core.erp_backend"),
    ("from divalto_agent", "from core.divalto_agent"),
    ("from sqlite_backend", "from core.sqlite_backend"),
    ("from settings", "from core.settings"),
    ("import settings", "import core.settings"),
    ("from api_server", "from app.server"),
]

SHIM_MAP: dict[str, str] = {
    "settings.py": "core.settings",
    "console_utils.py": "core.console_utils",
    "intent_contract.py": "core.intent_contract",
    "pipeline_router.py": "core.pipeline_router",
    "erp_backend.py": "core.erp_backend",
    "feedback_store.py": "core.feedback_store",
    "prompt_templates.py": "core.prompt_templates",
    "divalto_agent.py": "core.divalto_agent",
    "sqlite_backend.py": "core.sqlite_backend",
    "semantic_router.py": "routing.semantic_router",
    "semantic_routing.py": "routing.semantic_routing",
    "ollama_client.py": "llm.ollama_client",
    "rag_retriever.py": "llm.rag_retriever",
    "phase3_agent.py": "phase3.agent",
    "phase3_planner.py": "phase3.planner",
    "phase3_orchestrator.py": "phase3.orchestrator",
    "phase4_agent.py": "phase4.agent",
    "phase4_dataset.py": "phase4.dataset",
    "phase4_prefunctions.py": "phase4.prefunctions",
    "phase4_query_builder.py": "phase4.query_builder",
    "phase4_tools.py": "phase4.tools",
    "phase5_agent.py": "phase5.agent",
    "phase5_analytics.py": "phase5.analytics",
    "phase5_dates.py": "phase5.dates",
    "phase5_planner.py": "phase5.planner",
    "analytic_catalog.py": "analytics.catalog",
    "analytic_compiler.py": "analytics.compiler",
    "analytic_orchestrator.py": "analytics.orchestrator",
    "auto_olap_pipeline.py": "analytics.auto_olap_pipeline",
    "mdx_executor.py": "analytics.mdx_executor",
    "full_auto_run.py": "analytics.full_auto_run",
    "langgraph_agent.py": "agents.langgraph_agent",
    "api_server.py": "app.server",
}


def patch_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in IMPORT_REPLACEMENTS:
        text = text.replace(old, new)
    # ws_schemas path in divalto_agent
    text = text.replace(
        'Path(__file__).resolve().parent / "ws_schemas.json"',
        'Path(__file__).resolve().parent.parent / "config" / "ws_schemas.json"',
    )
    # generated_olap from analytics modules (one more parent)
    if "/analytics/" in str(path).replace("\\", "/"):
        text = re.sub(
            r'Path\(__file__\)\.resolve\(\)\.parent\s*/\s*"generated_olap"',
            'Path(__file__).resolve().parents[2] / "generated_olap"',
            text,
        )
        text = re.sub(
            r"Path\(__file__\)\.resolve\(\)\.parent\.parent\s*/\s*\"generated_olap\"",
            'Path(__file__).resolve().parents[2] / "generated_olap"',
            text,
        )
    # prompt_templates config path
    if "core/prompt_templates" in str(path).replace("\\", "/"):
        text = text.replace(
            'Path(__file__).resolve().parent / "config"',
            'Path(__file__).resolve().parent.parent / "config"',
        )
    if text != original:
        path.write_text(text, encoding="utf-8")


def main() -> None:
    packages = ["core", "routing", "llm", "phase3", "phase4", "phase5", "analytics", "agents", "app"]
    for pkg in packages:
        (SRC / pkg).mkdir(parents=True, exist_ok=True)
        init = SRC / pkg / "__init__.py"
        if not init.exists():
            init.write_text(f'"""{pkg} module."""\n', encoding="utf-8")

    for old, new in MOVES:
        src_path = SRC / old
        dst_path = SRC / new
        if not src_path.exists():
            continue
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        if dst_path.exists():
            dst_path.unlink()
        shutil.move(str(src_path), str(dst_path))

    for py in list(SRC.rglob("*.py")) + list((ROOT / "tests").rglob("*.py")):
        if "reorganize_src" in str(py):
            continue
        patch_file(py)

    for old, mod in SHIM_MAP.items():
        shim = SRC / old
        if old == "api_server.py":
            shim.write_text(
                '"""Compatibility entrypoint for uvicorn api_server:app."""\n'
                "from app.server import app\n\n"
                '__all__ = ["app"]\n',
                encoding="utf-8",
            )
            continue
        if not (SRC / old.replace(".py", "").replace(".json", "")).exists() and old.endswith(".py"):
            shim.write_text(
                f'"""Compatibility shim — prefer `{mod}`."""\n'
                f"from {mod} import *  # noqa: F403\n",
                encoding="utf-8",
            )

    # phase3 public API
    (SRC / "phase3" / "__init__.py").write_text(
        '"""Phase 3 — plan, execute, aggregate."""\n'
        "from phase3.agent import run_phase3\n\n"
        '__all__ = ["run_phase3"]\n',
        encoding="utf-8",
    )
    (SRC / "phase4" / "__init__.py").write_text(
        '"""Phase 4 — query builder & semantic analytics."""\n'
        "from phase4.agent import run_phase4\n\n"
        '__all__ = ["run_phase4"]\n',
        encoding="utf-8",
    )
    (SRC / "phase5" / "__init__.py").write_text(
        '"""Phase 5 — multi-call analytics."""\n'
        "from phase5.agent import run_phase5\n\n"
        '__all__ = ["run_phase5"]\n',
        encoding="utf-8",
    )
    print("Reorganization complete.")


if __name__ == "__main__":
    main()
