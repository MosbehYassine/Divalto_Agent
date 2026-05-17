from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping


_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "token",
        "authorization",
        "refresh_token",
        "client_secret",
        "secret",
    }
)


def redact_secrets(value: Any) -> Any:
    """Recursively redact obvious secret fields before persisting audits."""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, nested in value.items():
            lk = str(key).lower()
            if lk in _SENSITIVE_KEYS or lk.endswith("password"):
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = redact_secrets(nested)
        return sanitized
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


_audit_lock = threading.Lock()


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(redact_secrets(dict(payload)), ensure_ascii=False, default=str)
    with _audit_lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


@dataclass(slots=True)
class JsonlAuditSink:
    """Append-only JSONL sink (thread-safe) for run-level traceability."""

    path: Path

    def emit(self, record: Mapping[str, Any]) -> None:
        _append_jsonl(self.path, record)


def build_run_record(
    *,
    correlation_id: str,
    user_query: str | None,
    plan: list[dict[str, Any]],
    execution_result: Mapping[str, Any],
    final_answer: str | None,
    started_monotonic: float,
    governance_meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    duration_ms = max(0.0, (perf_counter() - started_monotonic) * 1000.0)
    return {
        "schema_version": "agent_run_v1",
        "correlation_id": correlation_id,
        "user_query": user_query,
        "plan": plan,
        "execution": dict(execution_result),
        "final_answer": final_answer,
        "duration_ms": round(duration_ms, 3),
        "governance": dict(governance_meta or {}),
    }
