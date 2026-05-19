"""
prompt_templates.py
===================
Load planner prompts from configurable JSON file.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.settings import PLANNER_PROMPT_TEMPLATES_PATH


def _templates_path() -> Path:
    if PLANNER_PROMPT_TEMPLATES_PATH.strip():
        return Path(PLANNER_PROMPT_TEMPLATES_PATH).resolve()
    return Path(__file__).resolve().parent.parent / "config" / "planner_prompt_templates.json"


def load_prompt_template(key: str) -> str:
    path = _templates_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing planner prompt template for key '{key}' in {path}")
    return value
