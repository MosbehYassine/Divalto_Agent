"""Project path helpers (src layout: agent_project/src/<module>/...)."""

from __future__ import annotations

from pathlib import Path

# agent_project/ (repository root for the app)
AGENT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = AGENT_ROOT / "src"
CONFIG_DIR = SRC_ROOT / "config"
DATASETS_DIR = AGENT_ROOT / "datasets"
GENERATED_OLAP_DIR = AGENT_ROOT / "generated_olap"
