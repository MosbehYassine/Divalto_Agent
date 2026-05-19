"""
Persist user feedback on assistant answers (thumbs up/down) as JSONL for future tuning.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from core.settings import FEEDBACK_JSONL_PATH

Rating = Literal["up", "down"]


def _default_feedback_path() -> Path:
    return Path(__file__).resolve().parent.parent / "datasets" / "chat_answer_feedback.jsonl"


def feedback_file_path() -> Path:
    raw = (FEEDBACK_JSONL_PATH or "").strip()
    return Path(raw) if raw else _default_feedback_path()


def append_answer_feedback(
    *,
    rating: Rating,
    user_query: str,
    assistant_answer: str,
    mode: str | None = None,
    conversation_id: str | None = None,
    message_id: str | None = None,
    chart_type: str | None = None,
    real_planner: bool | None = None,
) -> dict[str, Any]:
    if rating not in ("up", "down"):
        raise ValueError("rating must be 'up' or 'down'")

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rating": rating,
        "user_query": user_query.strip(),
        "assistant_answer": assistant_answer.strip(),
        "mode": mode,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "chart_type": chart_type,
        "real_planner": real_planner,
        "source": "frontend_chat",
    }

    path = feedback_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {"ok": True, "path": str(path), "rating": rating}
